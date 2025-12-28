from django.contrib import admin
from .models import SiteConfig, TeamMember

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    pass

@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'order', 'is_active', 'created_at')
    list_editable = ('order', 'is_active')
    search_fields = ('name', 'role')
