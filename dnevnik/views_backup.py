from django.http import FileResponse, HttpResponse

from .backup import BackupNotSupported, create_backup
from .permissions import admin_required


@admin_required
def preuzmi_backup(request):
    try:
        path = create_backup()
    except BackupNotSupported as exc:
        return HttpResponse(str(exc), status=400)
    except FileNotFoundError as exc:
        return HttpResponse(str(exc), status=404)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)
