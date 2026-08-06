from django.contrib import admin

from .models import ContentAgent, ContentItem, ContentRun

admin.site.register(ContentAgent)
admin.site.register(ContentRun)
admin.site.register(ContentItem)
