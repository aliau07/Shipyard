from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register('projects', views.ProjectViewSet, basename='project')
router.register('components', views.ComponentViewSet, basename='component')
router.register('dependencies', views.DependencyViewSet, basename='dependency')

urlpatterns = router.urls
