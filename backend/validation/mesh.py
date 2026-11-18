"""Анализ 3D-сетки на trimesh + numpy. Блокирующие ошибки E-01/E-02 поднимаются как DomainError."""
import io
import math
import struct
import zipfile

import numpy as np
from django.conf import settings

from config.exceptions import DomainError

ALLOWED = {'stl': 'STL', 'obj': 'OBJ', '3mf': '3MF'}
MAX_3MF_ENTRIES = 2000
MAX_3MF_RATIO = 100
OVERHANG_COS = 0.7071067811865476  # 45°
OVERHANG_RATIO_THRESHOLD = 0.05


def detect_format(file_name: str) -> str:
    if not file_name or '.' not in file_name:
        raise DomainError('E-01: Не указано расширение файла. Допустимы только STL, OBJ и 3MF.', 'E-01')
    ext = file_name.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED:
        raise DomainError(f'E-01: Формат .{ext} не поддерживается. Допустимы только STL, OBJ и 3MF.', 'E-01')
    return ALLOWED[ext]


def check_upload(file_name: str, data: bytes) -> str:
    """E-01 / E-02. Возвращает формат ('STL' | 'OBJ' | '3MF')."""
    fmt = detect_format(file_name)
    max_bytes = getattr(settings, 'MAX_UPLOAD_BYTES', 50 * 1024 * 1024)
    if len(data) > max_bytes:
        raise DomainError('E-01: Размер файла превышает 50 МБ.', 'E-01')
    if not data or len(data) < 16:
        raise DomainError('E-02: Файл пуст или повреждён.', 'E-02')
    head = data[:16]
    if head.startswith(b'ISO-10303') or head.startswith(b'%PDF') or head.startswith(b'MZ'):
        raise DomainError('E-01: Содержимое файла не соответствует формату STL, OBJ или 3MF.', 'E-01')
    if fmt == '3MF':
        if not data.startswith(b'PK\x03\x04') and not data.startswith(b'PK'):
            raise DomainError('E-01: Содержимое файла не соответствует формату 3MF.', 'E-01')
        try:
            with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
                infos = zf.infolist()
                if not infos or len(infos) > MAX_3MF_ENTRIES:
                    raise DomainError('E-02: Недопустимая структура архива 3MF.', 'E-02')
                max_unpacked = getattr(settings, 'MAX_3MF_UNPACKED_BYTES', 500 * 1024 * 1024)
                total = 0
                has_model = False
                for i in infos:
                    if i.flag_bits & 0x1:
                        raise DomainError('E-02: Зашифрованные архивы 3MF не поддерживаются.', 'E-02')
                    total += i.file_size
                    if i.compress_size and i.file_size / i.compress_size > MAX_3MF_RATIO and i.file_size > 1024 * 1024:
                        raise DomainError('E-02: Подозрительная степень сжатия в архиве 3MF (защита от zip-bomb).', 'E-02')
                    if i.filename.lower().endswith('.model'):
                        has_model = True
                if total > max_unpacked:
                    raise DomainError('E-02: Архив 3MF превышает допустимый размер распаковки.', 'E-02')
                if not has_model:
                    raise DomainError('E-02: В архиве 3MF отсутствует 3D-модель.', 'E-02')
                if zf.testzip() is not None:
                    raise DomainError('E-02: Файл 3MF повреждён.', 'E-02')
        except DomainError:
            raise
        except Exception:
            raise DomainError('E-02: Архив 3MF повреждён и не может быть прочитан.', 'E-02')
    elif fmt == 'STL':
        head_sample = data[:512].lstrip()
        is_ascii = head_sample.lower().startswith(b'solid') and b'facet' in data[:4096].lower()
        if is_ascii:
            if b'endsolid' not in data[-1024:].lower():
                raise DomainError('E-02: Текстовый файл STL обрезан или повреждён.', 'E-02')
        else:
            if len(data) < 84:
                raise DomainError('E-02: Бинарный файл STL обрезан или повреждён.', 'E-02')
            n = struct.unpack('<I', data[80:84])[0]
            if n == 0 or len(data) < 84 + 50 * n:
                raise DomainError('E-02: Бинарный файл STL обрезан или повреждён.', 'E-02')
    else:  # OBJ
        if b'\x00' in data[:2048]:
            raise DomainError('E-01: Содержимое файла не соответствует формату OBJ.', 'E-01')
        try:
            sample = data[:4096].decode('utf-8', errors='replace')
            if 'v ' not in sample and '\nv ' not in sample and 'f ' not in sample:
                raise DomainError('E-02: В файле OBJ не найдены вершины и грани.', 'E-02')
        except Exception:
            raise DomainError('E-02: Файл OBJ повреждён.', 'E-02')
    return fmt


def analyze(data: bytes, fmt: str) -> dict:
    """Загружает сетку и считает метрики. E-02, если сетку прочитать нельзя."""
    import trimesh
    try:
        loaded = trimesh.load(io.BytesIO(data), file_type=fmt.lower(), force=None)
    except Exception:
        raise DomainError('E-02: Не удалось разобрать 3D-сетку модели.', 'E-02')

    meshes = []
    if isinstance(loaded, trimesh.Scene):
        for g in loaded.geometry.values():
            if isinstance(g, trimesh.Trimesh) and len(g.faces) > 0:
                meshes.append(g)
    elif isinstance(loaded, trimesh.Trimesh) and len(loaded.faces) > 0:
        meshes.append(loaded)

    if not meshes:
        raise DomainError('E-02: Модель не содержит полигональной сетки.', 'E-02')

    combined = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    try:
        bodies = combined.split(only_watertight=False)
        body_count = max(len(bodies), len(meshes), 1)
    except Exception:
        body_count = max(len(meshes), 1)

    watertight = bool(combined.is_watertight)
    repaired = False
    if not watertight:
        try:
            trimesh.repair.fill_holes(combined)
            trimesh.repair.fix_normals(combined)
            repaired = bool(combined.is_watertight)
        except Exception:
            pass

    extents = [float(x) for x in combined.extents] if combined.extents is not None else [0.0, 0.0, 0.0]
    vol_mm3 = abs(float(combined.volume)) if combined.faces is not None and len(combined.faces) > 0 else 0.0
    if (not math.isfinite(vol_mm3) or vol_mm3 <= 0) and all(x > 0 for x in extents):
        vol_mm3 = float(combined.convex_hull.volume) if len(combined.vertices) >= 4 else 0.0
    volume_cm3 = round(vol_mm3 / 1000.0, 4)

    overhang_ratio = 0.0
    try:
        normals = combined.face_normals
        areas = combined.area_faces
        total_area = float(np.sum(areas))
        if total_area > 0:
            cos45 = -math.cos(math.radians(45.0))
            overhang_mask = normals[:, 2] < cos45
            overhang_mask_area = float(np.sum(areas[overhang_mask]))
            overhang_ratio = round(overhang_mask_area / total_area, 4)
    except Exception:
        overhang_ratio = 0.0

    surface_cm2 = float(combined.area) / 100.0 if combined.area else 0.0
    min_dim = min(extents) if extents else 0.0
    thickness = min(min_dim, (vol_mm3 / float(combined.area)) * 2.0) if combined.area else min_dim

    return {
        'bbox': [round(x, 2) for x in extents],
        'volume_cm3': volume_cm3,
        'body_count': int(body_count),
        'analysis': {
            'watertight': watertight,
            'repaired': repaired,
            'min_thickness_mm': round(float(thickness), 4),
            'overhang_ratio': round(overhang_ratio, 4),
            'surface_cm2': round(surface_cm2, 2),
        },
    }

