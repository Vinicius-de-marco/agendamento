"""Mensagens de WhatsApp: lembrete 24h antes para o cliente e avisos para o dono."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import formats, timezone

from .models import Agendamento
from .whatsapp import enviar_mensagem

logger = logging.getLogger(__name__)

ANTECEDENCIA_LEMBRETE = timedelta(hours=24)
STATUS_ATIVOS = [Agendamento.Status.AGENDADO, Agendamento.Status.CONFIRMADO]
_SALT_TOKEN = 'agenda.agendamento'


def gerar_token(agendamento):
    return signing.dumps(agendamento.pk, salt=_SALT_TOKEN)


def ler_token(token):
    """Retorna o id do agendamento do token, ou None se o token for inválido."""
    try:
        return signing.loads(token, salt=_SALT_TOKEN)
    except signing.BadSignature:
        return None


def link_agendamento(agendamento):
    """Link absoluto da página onde o cliente confirma ou cancela."""
    caminho = reverse(
        'agenda:gerenciar_agendamento', args=[agendamento.negocio.slug, gerar_token(agendamento)]
    )
    return settings.SITE_URL + caminho


def _quando(agendamento):
    inicio = timezone.localtime(agendamento.inicio)
    dia_semana = formats.date_format(inicio, 'l').lower()
    return f"{dia_semana}, {inicio:%d/%m} às {inicio:%H:%M}"


def texto_lembrete(agendamento):
    return (
        f'Olá, {agendamento.cliente.nome}! Lembrete do seu horário em {agendamento.negocio.nome}:\n'
        f'{agendamento.servico.nome}, {_quando(agendamento)}.\n\n'
        f'Para confirmar ou cancelar, acesse: {link_agendamento(agendamento)}'
    )


def texto_aviso_dono(agendamento, evento):
    return (
        f'{evento}: {agendamento.cliente.nome} ({agendamento.cliente.whatsapp}) – '
        f'{agendamento.servico.nome}, {_quando(agendamento)}.'
    )


def agendamentos_para_lembrar(agora=None):
    """Agendamentos ativos que começam nas próximas 24h e ainda não receberam lembrete."""
    agora = agora or timezone.now()
    return Agendamento.objects.filter(
        status__in=STATUS_ATIVOS,
        inicio__gt=agora,
        inicio__lte=agora + ANTECEDENCIA_LEMBRETE,
        lembrete_enviado_em__isnull=True,
    ).select_related('negocio', 'servico', 'cliente')


def enviar_lembrete(agendamento, agora=None):
    """Envia o lembrete e marca como enviado. Retorna False se outro processo já
    enviou ou se o agendamento foi cancelado.

    A marcação é feita antes do envio (update condicional) para que duas execuções
    simultâneas do comando não mandem o lembrete duas vezes, nem para um agendamento
    cancelado depois de ter sido listado. Se o envio falhar, a marcação é desfeita para tentar de novo na próxima execução.
    """
    agora = agora or timezone.now()
    marcado = Agendamento.objects.filter(
        pk=agendamento.pk, status__in=STATUS_ATIVOS, lembrete_enviado_em__isnull=True
    ).update(lembrete_enviado_em=agora)
    if not marcado:
        return False
    try:
        enviar_mensagem(agendamento.cliente.whatsapp, texto_lembrete(agendamento))
    except Exception:
        Agendamento.objects.filter(pk=agendamento.pk).update(lembrete_enviado_em=None)
        raise
    agendamento.lembrete_enviado_em = agora
    return True


def avisar_dono(agendamento, evento):
    """Avisa o dono no WhatsApp do negócio. Falhas só vão para o log: o aviso
    não pode impedir o cliente de agendar ou cancelar."""
    try:
        enviar_mensagem(agendamento.negocio.whatsapp, texto_aviso_dono(agendamento, evento))
    except Exception:
        logger.exception('Falha ao avisar o dono sobre o agendamento %s', agendamento.pk)
