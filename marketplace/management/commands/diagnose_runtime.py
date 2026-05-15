from django.core.management.base import BaseCommand, CommandError

from helperlearner_root.runtime_checks import collect_runtime_snapshot


class Command(BaseCommand):
    help = "Run runtime diagnostics for database/cache/channels/celery/logging/AI config."

    def handle(self, *args, **options):
        snapshot = collect_runtime_snapshot()
        self.stdout.write(f"Runtime status: {snapshot['status']}")
        self.stdout.write(f"Checked at: {snapshot['checked_at']}")

        for check_name, payload in snapshot["checks"].items():
            label = f"[{check_name}]"
            detail = payload.get("detail", "")
            if payload["ok"]:
                self.stdout.write(self.style.SUCCESS(f"{label} OK - {detail}"))
            elif payload["critical"]:
                self.stdout.write(self.style.ERROR(f"{label} CRITICAL - {detail}"))
            else:
                self.stdout.write(self.style.WARNING(f"{label} WARN - {detail}"))

        if snapshot["critical_failures"]:
            raise CommandError(
                "Critical runtime checks failed: " + ", ".join(snapshot["critical_failures"])
            )

        if snapshot["warnings"]:
            self.stdout.write(
                self.style.WARNING(
                    "Non-critical warnings: " + ", ".join(snapshot["warnings"])
                )
            )

        self.stdout.write(self.style.SUCCESS("Runtime diagnostics completed."))

