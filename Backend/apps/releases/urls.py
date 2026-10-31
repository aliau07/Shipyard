from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register('releases', views.ReleaseViewSet, basename='release')

urlpatterns = router.urls
