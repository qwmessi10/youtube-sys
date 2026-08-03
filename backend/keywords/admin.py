from django.contrib import admin

from .models import GlobalSetting, KeywordResult, KeywordRun

admin.site.register(GlobalSetting)
admin.site.register(KeywordRun)
admin.site.register(KeywordResult)

