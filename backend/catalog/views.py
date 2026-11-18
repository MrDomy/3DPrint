from rest_framework.response import Response
from rest_framework.views import APIView

from config.exceptions import DomainError
from config.permissions import IsClientOrManager, IsManager

from . import services
from .models import (Color, DeliveryMethod, Material, PickupPoint, PostProcessing, Printer, QualityProfile,
                     Technology, Workshop)


def _s(x):
    return str(x)


def dto_technology(t):
    return {'id': _s(t.id), 'code': t.code, 'name': t.name}


def _materials(q):
    return [{'id': _s(m.id), 'name': m.name,
             'technologies': [_s(t.id) for t in m.technologies.all()],
             'colors': [_s(c.id) for c in m.colors.all()]} for m in q.prefetch_related('technologies', 'colors')]


CATALOG = {
    'technologies': lambda: [dto_technology(t) for t in Technology.objects.filter(is_active=True).order_by('code')],
    'materials': lambda: _materials(Material.objects.filter(is_active=True).order_by('name')),
    'quality-profiles': lambda: [{'id': _s(q.id), 'technology': _s(q.technology_id), 'name': q.name,
                                  'layer_height_mm': float(q.layer_height_mm)}
                                 for q in QualityProfile.objects.order_by('technology__code', 'layer_height_mm')],
    'colors': lambda: [{'id': _s(c.id), 'name': c.name, 'hex': c.hex} for c in Color.objects.order_by('name')],
    'post-processing': lambda: [{'id': _s(p.id), 'name': p.name, 'price': float(p.price), 'hours': float(p.hours)}
                                for p in PostProcessing.objects.filter(is_active=True)],
    'delivery-methods': lambda: [{'id': _s(d.id), 'type': d.type, 'name': d.name, 'price': float(d.price),
                                  'days': d.days} for d in DeliveryMethod.objects.filter(is_active=True)],
    'pickup-points': lambda: [{'id': _s(p.id), 'delivery_method': _s(p.delivery_method_id), 'name': p.name,
                               'address': p.address} for p in PickupPoint.objects.filter(is_active=True)],
}


class CatalogView(APIView):
    permission_classes = [IsClientOrManager]

    def get(self, request, name):
        if name == 'compatibility':
            return Response(services.compatibility_matrix())
        if name not in CATALOG:
            raise DomainError('Справочник не найден.', 'not_found', 404)
        return Response(CATALOG[name]())


class PrintersView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        return Response([{'id': _s(p.id), 'name': p.name, 'workshop': p.workshop.name, 'workshop_id': _s(p.workshop_id),
                          'technology': p.technology.code, 'dims': [float(p.max_x), float(p.max_y), float(p.max_z)],
                          'specialization': p.specialization, 'status': p.status,
                          'materials': [m.name for m in p.materials.all()]}
                         for p in Printer.objects.select_related('workshop', 'technology')
                         .prefetch_related('materials').order_by('name')])


class WorkshopsView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        return Response([{'id': _s(w.id), 'name': w.name, 'address': w.address, 'is_main': w.is_main}
                         for w in Workshop.objects.all()])
