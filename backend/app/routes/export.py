"""Export route — download HTML report or ZIP bundle for a completed run."""

from enum import StrEnum

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..export.bundle import generate_html_report, generate_zip_bundle

router = APIRouter(prefix="/api/runs", tags=["export"])


class ExportFormat(StrEnum):
    HTML = "html"
    ZIP = "zip"


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    format: ExportFormat = Query(default=ExportFormat.HTML, alias="format"),
) -> Response:
    """Export a run as a self-contained HTML report or ZIP bundle."""
    try:
        if format == ExportFormat.HTML:
            html = await generate_html_report(run_id)
            return Response(
                content=html,
                media_type="text/html",
                headers={
                    "Content-Disposition": f'attachment; filename="vigil-report-{run_id[:8]}.html"',
                },
            )

        zip_bytes = await generate_zip_bundle(run_id)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="vigil-report-{run_id[:8]}.zip"',
            },
        )

    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
