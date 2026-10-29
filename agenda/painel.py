"""Painel do dono: agenda do dia, serviços, horário de funcionamento e bloqueios."""

from datetime import date, datetime, time, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import BloqueioForm, HorarioFuncionamentoForm, ServicoForm
from .models import Agendamento, Bloqueio, HorarioFuncionamento, Servico


def painel_do_dono(view):
    """Exige login e entrega à view o negócio do usuário (o MVP usa um negócio por dono)."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        negocio = request.user.negocios.first()
        if negocio is None:
            return render(request, 'agenda/painel/sem_negocio.html', status=403)
        return view(request, negocio, *args, **kwargs)

    return wrapper


def _limites_do_dia(dia):
    inicio = datetime.combine(dia, time.min, tzinfo=timezone.get_default_timezone())
    return inicio, inicio + timedelta(days=1)


# Agenda do dia


@painel_do_dono
def agenda(request, negocio):
    hoje = timezone.localdate()
    try:
        dia = date.fromisoformat(request.GET.get('dia', ''))
    except ValueError:
        dia = hoje
    inicio, fim = _limites_do_dia(dia)
    return render(
        request,
        'agenda/painel/agenda.html',
        {
            'negocio': negocio,
            'dia': dia,
            'hoje': hoje,
            'anterior': dia - timedelta(days=1),
            'proximo': dia + timedelta(days=1),
            'agendamentos': negocio.agendamentos.filter(inicio__gte=inicio, inicio__lt=fim)
            .select_related('cliente', 'servico'),
            'bloqueios': negocio.bloqueios.filter(inicio__lt=fim, fim__gt=inicio),
        },
    )


@require_POST
@painel_do_dono
def alterar_status(request, negocio, pk):
    agendamento = get_object_or_404(Agendamento, pk=pk, negocio=negocio)
    novo = request.POST.get('status')
    if novo not in (Agendamento.Status.CONFIRMADO, Agendamento.Status.CANCELADO):
        return HttpResponseBadRequest('Status inválido.')
    # Reativar um cancelado poderia colidir com quem pegou o horário depois
    if agendamento.status == Agendamento.Status.CANCELADO:
        messages.error(request, 'Este agendamento já foi cancelado.')
    else:
        agendamento.status = novo
        agendamento.save(update_fields=['status'])
        messages.success(
            request,
            f'Agendamento de {agendamento.cliente.nome} {agendamento.get_status_display().lower()}.',
        )
    dia = timezone.localdate(agendamento.inicio)
    return redirect(f"{reverse('painel:agenda')}?dia={dia.isoformat()}")


# Serviços


@painel_do_dono
def servicos(request, negocio):
    return render(
        request,
        'agenda/painel/servicos.html',
        {'negocio': negocio, 'servicos': negocio.servicos.all()},
    )


@painel_do_dono
def servico_form(request, negocio, pk=None):
    servico = get_object_or_404(Servico, pk=pk, negocio=negocio) if pk else Servico(negocio=negocio)
    form = ServicoForm(request.POST or None, instance=servico)
    if form.is_valid():
        form.save()
        messages.success(request, f'Serviço "{servico.nome}" salvo.')
        return redirect('painel:servicos')
    titulo = f'Editar {servico.nome}' if pk else 'Novo serviço'
    return _render_form(request, negocio, form, titulo, 'painel:servicos')


# Horário de funcionamento


@painel_do_dono
def horarios(request, negocio):
    return render(
        request,
        'agenda/painel/horarios.html',
        {'negocio': negocio, 'horarios': negocio.horarios.all()},
    )


@painel_do_dono
def horario_novo(request, negocio):
    form = HorarioFuncionamentoForm(
        request.POST or None, instance=HorarioFuncionamento(negocio=negocio)
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Horário adicionado.')
        return redirect('painel:horarios')
    return _render_form(request, negocio, form, 'Novo horário de funcionamento', 'painel:horarios')


@require_POST
@painel_do_dono
def horario_excluir(request, negocio, pk):
    get_object_or_404(HorarioFuncionamento, pk=pk, negocio=negocio).delete()
    messages.success(request, 'Horário removido.')
    return redirect('painel:horarios')


# Bloqueios


@painel_do_dono
def bloqueios(request, negocio):
    return render(
        request,
        'agenda/painel/bloqueios.html',
        {'negocio': negocio, 'bloqueios': negocio.bloqueios.filter(fim__gt=timezone.now())},
    )


@painel_do_dono
def bloqueio_novo(request, negocio):
    form = BloqueioForm(request.POST or None, instance=Bloqueio(negocio=negocio))
    if form.is_valid():
        bloqueio = form.save()
        messages.success(request, 'Bloqueio criado.')
        conflitos = (
            negocio.agendamentos.filter(inicio__lt=bloqueio.fim, fim__gt=bloqueio.inicio)
            .exclude(status=Agendamento.Status.CANCELADO)
            .count()
        )
        if conflitos:
            messages.warning(
                request,
                f'Já existem {conflitos} agendamento(s) nesse período. '
                'Eles não foram cancelados: avise os clientes ou cancele pela agenda.',
            )
        return redirect('painel:bloqueios')
    return _render_form(request, negocio, form, 'Novo bloqueio', 'painel:bloqueios')


@require_POST
@painel_do_dono
def bloqueio_excluir(request, negocio, pk):
    get_object_or_404(Bloqueio, pk=pk, negocio=negocio).delete()
    messages.success(request, 'Bloqueio removido.')
    return redirect('painel:bloqueios')


def _render_form(request, negocio, form, titulo, voltar):
    return render(
        request,
        'agenda/painel/form.html',
        {'negocio': negocio, 'form': form, 'titulo': titulo, 'voltar': voltar},
    )
