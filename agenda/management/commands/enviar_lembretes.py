import logging

from django.core.management.base import BaseCommand

from agenda.lembretes import agendamentos_para_lembrar, enviar_lembrete

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envia o lembrete no WhatsApp para agendamentos das próximas 24h (rodar via cron).'

    def handle(self, *args, **options):
        enviados = falhas = 0
        for agendamento in agendamentos_para_lembrar():
            try:
                if enviar_lembrete(agendamento):
                    enviados += 1
            except Exception:
                # Um envio com problema não impede os outros; tenta de novo na próxima execução.
                # O log (stderr) leva o traceback completo para a saída do cron.
                falhas += 1
                logger.exception('Falha no lembrete do agendamento %s', agendamento.pk)
        self.stdout.write(f'Lembretes enviados: {enviados}. Falhas: {falhas}.')
