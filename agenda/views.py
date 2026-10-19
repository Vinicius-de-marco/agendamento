from django.shortcuts import get_object_or_404, render

from .models import Negocio


def pagina_negocio(request, slug):
    negocio = get_object_or_404(Negocio, slug=slug)
    return render(
        request,
        'agenda/pagina_negocio.html',
        {
            'negocio': negocio,
            'servicos': negocio.servicos.filter(ativo=True),
            'horarios': negocio.horarios.all(),
        },
    )
