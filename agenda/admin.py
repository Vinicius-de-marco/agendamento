from django.contrib import admin

from .models import Agendamento, Bloqueio, Cliente, HorarioFuncionamento, Negocio, Servico


class ServicoInline(admin.TabularInline):
    model = Servico
    extra = 0


class HorarioFuncionamentoInline(admin.TabularInline):
    model = HorarioFuncionamento
    extra = 0


@admin.register(Negocio)
class NegocioAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug', 'dono', 'whatsapp']
    search_fields = ['nome', 'slug']
    prepopulated_fields = {'slug': ['nome']}
    inlines = [ServicoInline, HorarioFuncionamentoInline]


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'negocio', 'duracao_minutos', 'preco', 'ativo']
    list_filter = ['negocio', 'ativo']
    search_fields = ['nome']


@admin.register(HorarioFuncionamento)
class HorarioFuncionamentoAdmin(admin.ModelAdmin):
    list_display = ['negocio', 'dia_semana', 'abertura', 'fechamento']
    list_filter = ['negocio', 'dia_semana']


@admin.register(Bloqueio)
class BloqueioAdmin(admin.ModelAdmin):
    list_display = ['negocio', 'inicio', 'fim', 'motivo']
    list_filter = ['negocio']
    date_hierarchy = 'inicio'


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'whatsapp', 'negocio']
    list_filter = ['negocio']
    search_fields = ['nome', 'whatsapp']


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ['inicio', 'fim', 'cliente', 'servico', 'negocio', 'status']
    list_filter = ['negocio', 'status']
    search_fields = ['cliente__nome', 'cliente__whatsapp']
    date_hierarchy = 'inicio'
    readonly_fields = ['fim', 'lembrete_enviado_em']
    list_select_related = ['cliente', 'servico', 'negocio']
