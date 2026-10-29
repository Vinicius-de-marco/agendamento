"""Envio de mensagens de WhatsApp.

O provedor é escolhido em settings.WHATSAPP_BACKEND (caminho da classe). Cada backend
implementa enviar(numero, texto) e levanta exceção se a mensagem não puder ser enviada.
Para usar um provedor real (Cloud API, Twilio...), basta criar outra classe com esse método.
"""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class ConsoleBackend:
    """Não envia nada: só registra a mensagem no log (desenvolvimento)."""

    def enviar(self, numero, texto):
        logger.info('WhatsApp para %s:\n%s', numero, texto)


class MemoriaBackend:
    """Guarda as mensagens em MemoriaBackend.enviadas (testes)."""

    enviadas = []

    def enviar(self, numero, texto):
        self.enviadas.append((numero, texto))


def enviar_mensagem(numero, texto):
    backend = import_string(settings.WHATSAPP_BACKEND)()
    backend.enviar(numero, texto)
