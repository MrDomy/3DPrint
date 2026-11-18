"""Анализ 3D-сетки на trimesh + numpy. Блокирующие ошибки E-01/E-02 поднимаются как DomainError."""
import io
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
    ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
    if ext not in ALLOWED:
        raise DomainError('E-01: Допустимы только файлы STL, OBJ и 3MF.', 'E-01')
    return ALLOWED[ext]


def check_upload(file_name: str, data: bytes) -> str:
    """E-01 / E-02. Возвращает формат ('STL' | 'OBJ' | '3MF')."""
    fmt = detect_format(file_name)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise DomainError('E-01: Размер файла превышает 50 МБ.', 'E-01')
    if not data:
        raise DomainError('E-02: Файл пуст.', 'E-02')
    head = data[:16]
    if head.startswith(b'ISO-10303') or head.startswith(b'%PDF') or head.startswith(b'MZ'):
        raise DomainError('E-01: Содержимое файла не соответствует формату STL, OBJ или 3MF.', 'E-01')
    if fmt == '3MF':
        if not data.startswith(b'PK'):
            raise DomainError('E-01: Содержимое файла не соответствует формату 3MF.', 'E-01')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_3MF_ENTRIES:
                    raise DomainError('E-02: Архив 3MF содержит слишком много файлов.', 'E-02')
                total = 0
                for i in infos:
                    if i.flag_bits & 0x1:
                        raise DomainError('E-02: Зашифрованные архивы 3MF не поддерживаются.', 'E-02')
                    total += i.file_size
                    if i.compress_size and i.file_size / i.compress_size > MAX_3MF_RATIO and i.file_size > 1024 * 1024:
                        raise DomainError('E-02: Подозрительная степень сжатия в архиве 3MF.', 'E-02')
                if total > settings.MAX_3MF_UNPACKED_BYTES:
                    raise DomainError('E-02: Архив 3MF превышает допустимый размер распаковки.', 'E-02')
                if zf.testzip() is not None:
                    raise DomainError('E-02: Файл 3MF повреждён.', 'E-02')
        except zipfile.BadZipFile:
            raise DomainError('E-02: Файл 3MF повреждён или не читается.', 'E-02')
    elif fmt == 'STL':
        is_ascii = data.lstrip().startswith(b'solid') and b'facet' in data[:4096]
        if not is_ascii:
            if len(data) < 84:
                raise DomainError('E-02: Файл STL повреждён (слишком короткий).', 'E-02')
            n = struct.unpack('<I', data[80:84])[0]
            if len(data) != 84 + 50 * n:
                raise DomainError('E-02: Файл STL повреждён или усечён.', 'E-02')
    else:  # OBJ
        if b'\x00' in data[:2048]:
            raise DomainError('E-01: Содержимое файла не соответствует формату OBJ.', 'E-01')
    return fmt


def analyze(data: bytes, fmt: str) -> dict:
    """Загружает сетку и считает метрики. E-02, если сетку прочитать нельзя."""
    import trimesh
    try:
        mesh = trimesh.load(io.BytesIO(data), file_type=fmt.lower(), force='mesh')
    except Exception:
        raise DomainError('E-02: Не удалось прочитать 3D-модель.', 'E-02')
    if mesh is None or not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
        raise DomainError('E-02: Модель не содержит геометрии.', 'E-02')

    watertight_orig = bool(mesh.is_watertight)
    repaired = False
    if not watertight_orig:
        try:
            trimesh.repair.fix_normals(mesh)
            trimesh.repair.fill_holes(mesh)
            repaired = bool(mesh.is_watertight)
        except Exception:
            pass
    try:
        bodies = mesh.split(only_watertight=False)
        body_count = len(bodies)
    except Exception:
        body_count = 1
    extents = [float(x) for x in mesh.extents]
    volume_mm3 = float(mesh.volume) if mesh.is_watertight else float(abs(mesh.volume))
    volume_cm3 = volume_mm3 / 1000.0

    # Эвристика толщины стенки: 2V/A для замкнутых сеток, иначе минимальный габарит
    area = float(mesh.area) or 1.0
    thickness = 2.0 * volume_mm3 / area if (mesh.is_watertight and volume_mm3 > 0) else min(extents)
    thickness = min(thickness, min(extents)) if not mesh.is_watertight else thickness

    # Нависания > 45° (исключая грани, лежащие на столе)
    normals = np.asarray(mesh.face_normals)
    areas = np.asarray(mesh.area_faces)
    zmin = float(mesh.bounds[0][2])
    centers_z = np.asarray(mesh.triangles_center)[:, 2]
    off_bed = centers_z > zmin + 0.5
    overhang = (normals[:, 2] < -OVERHANG_COS) & off_bed
    overhang_ratio = float(areas[overhang].sum() / areas.sum()) if areas.sum() > 0 else 0.0

    return {
        'bbox': extents, 'volume_cm3': volume_cm3, 'body_count': int(body_count),
        'analysis': {
            'watertight': watertight_orig, 'repaired': repaired,
            'min_thickness_mm': round(float(thickness), 4),
            'overhang_ratio': round(overhang_ratio, 4),
        },
    }
