"""Cálculo dos horários livres para agendar um serviço."""

from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Agendamento, Bloqueio

# Os horários oferecidos começam a cada PASSO_MINUTOS a partir da abertura.
PASSO_MINUTOS = 30


def horarios_livres(servico, dia, agora=None, passo_minutos=PASSO_MINUTOS):
    """Retorna os inícios (datetimes no fuso do projeto) em que `servico` cabe no `dia`.

    Um horário é livre quando o serviço inteiro cabe numa faixa de funcionamento,
    não colide com agendamento não cancelado nem com bloqueio, e começa depois de `agora`.
    """
    if not servico.ativo:
        return []

    fuso = timezone.get_default_timezone()
    agora = agora or timezone.now()
    negocio = servico.negocio
    duracao = timedelta(minutes=servico.duracao_minutos)
    passo = timedelta(minutes=passo_minutos)

    inicio_dia = datetime.combine(dia, time.min, tzinfo=fuso)
    fim_dia = inicio_dia + timedelta(days=1)
    no_dia = {'negocio': negocio, 'inicio__lt': fim_dia, 'fim__gt': inicio_dia}
    ocupados = list(
        Agendamento.objects.filter(**no_dia)
        .exclude(status=Agendamento.Status.CANCELADO)
        .values_list('inicio', 'fim')
    )
    ocupados += Bloqueio.objects.filter(**no_dia).values_list('inicio', 'fim')

    livres = []
    for faixa in negocio.horarios.filter(dia_semana=dia.weekday()):
        inicio = datetime.combine(dia, faixa.abertura, tzinfo=fuso)
        fechamento = datetime.combine(dia, faixa.fechamento, tzinfo=fuso)
        while inicio + duracao <= fechamento:
            fim = inicio + duracao
            colide = any(o_inicio < fim and o_fim > inicio for o_inicio, o_fim in ocupados)
            if inicio > agora and not colide:
                livres.append(inicio)
            inicio += passo
    return sorted(livres)


def horario_esta_livre(servico, inicio, agora=None, passo_minutos=PASSO_MINUTOS):
    """Confere se `inicio` é um dos horários livres (use antes de criar o agendamento)."""
    inicio_local = timezone.localtime(inicio, timezone.get_default_timezone())
    livres = horarios_livres(servico, inicio_local.date(), agora=agora, passo_minutos=passo_minutos)
    return inicio_local in livres
