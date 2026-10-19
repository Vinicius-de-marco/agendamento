from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AgendamentoForm
from .horarios import horario_esta_livre, horarios_livres
from .models import Agendamento, Cliente, Negocio, Servico

# Quantos dias à frente o cliente pode agendar (contando hoje)
DIAS_PARA_AGENDAR = 14


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


def _servico_ativo(slug, servico_id):
    return get_object_or_404(
        Servico.objects.select_related('negocio'),
        pk=servico_id,
        negocio__slug=slug,
        ativo=True,
    )


def _dias_de_atendimento(negocio):
    """Próximos dias (a partir de hoje) em que o negócio tem horário de funcionamento."""
    dias_semana = set(negocio.horarios.values_list('dia_semana', flat=True))
    hoje = timezone.localdate()
    proximos = (hoje + timedelta(days=n) for n in range(DIAS_PARA_AGENDAR))
    return [dia for dia in proximos if dia.weekday() in dias_semana]


def escolher_horario(request, slug, servico_id):
    servico = _servico_ativo(slug, servico_id)
    dias = _dias_de_atendimento(servico.negocio)

    try:
        dia = date.fromisoformat(request.GET.get('dia', ''))
    except ValueError:
        dia = None
    if dia not in dias:
        dia = dias[0] if dias else None

    contexto = {
        'negocio': servico.negocio,
        'servico': servico,
        'dias': dias,
        'dia': dia,
        'horarios': horarios_livres(servico, dia) if dia else [],
    }
    # Ao trocar de dia pelo HTMX, só a lista de horários é renderizada de novo
    if request.headers.get('HX-Request'):
        return render(request, 'agenda/_horarios.html', contexto)
    return render(request, 'agenda/escolher_horario.html', contexto)


def confirmar_agendamento(request, slug, servico_id):
    servico = _servico_ativo(slug, servico_id)
    negocio = servico.negocio

    voltar = redirect('agenda:escolher_horario', slug=negocio.slug, servico_id=servico.pk)

    if request.method == 'POST':
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            agendamento = _criar_agendamento(servico, form.cleaned_data)
            if agendamento:
                request.session['agendamento_id'] = agendamento.pk
                return redirect('agenda:agendamento_concluido', slug=negocio.slug)
            form.add_error(None, 'Esse horário acabou de ser ocupado. Escolha outro.')
        inicio = form.cleaned_data.get('inicio')
        if inicio is None:
            return voltar
    else:
        inicio = _ler_inicio(request.GET.get('inicio'))
        if inicio is None or not horario_esta_livre(servico, inicio):
            return voltar
        form = AgendamentoForm(initial={'inicio': inicio})

    return render(
        request,
        'agenda/confirmar_agendamento.html',
        {'negocio': negocio, 'servico': servico, 'form': form, 'inicio': inicio},
    )


def _ler_inicio(valor):
    """Converte o horário vindo da URL (ex: 2026-10-20T09:00, hora local) em datetime."""
    try:
        return forms.DateTimeField().clean(valor)
    except ValidationError:
        return None


def _criar_agendamento(servico, dados):
    """Cria o agendamento se o horário ainda estiver livre; senão retorna None."""
    negocio = servico.negocio
    with transaction.atomic():
        # Trava o negócio para que duas reservas simultâneas não peguem o mesmo horário
        # (efetivo no PostgreSQL; o SQLite já serializa as escritas)
        Negocio.objects.select_for_update().get(pk=negocio.pk)
        if not horario_esta_livre(servico, dados['inicio']):
            return None
        cliente, _ = Cliente.objects.update_or_create(
            negocio=negocio, whatsapp=dados['whatsapp'], defaults={'nome': dados['nome']}
        )
        return Agendamento.objects.create(
            negocio=negocio, servico=servico, cliente=cliente, inicio=dados['inicio']
        )


def agendamento_concluido(request, slug):
    agendamento = (
        Agendamento.objects.select_related('negocio', 'servico', 'cliente')
        .filter(pk=request.session.get('agendamento_id'), negocio__slug=slug)
        .first()
    )
    if agendamento is None:
        return redirect('agenda:pagina_negocio', slug=slug)
    return render(request, 'agenda/agendamento_concluido.html', {'agendamento': agendamento})
