"""
TDW management command: seed a DEFAULT demo project so a fresh Label Studio
instance doesn't show the empty "Heidi doesn't see any projects here!" state on
first login.

Idempotent and conservative:
  * Does NOTHING if the organization already has ANY project (so it never
    duplicates and never reappears after a user deletes it... unless the org is
    empty again — see TDW_SEED_PROJECT_ALWAYS below).
  * Creates ONE text-classification sample project owned by the org, published,
    with a couple of example tasks so the user can click straight into labeling.

Env:
  TDW_SEED_PROJECT        '0'/'false' to disable entirely (default: enabled).
  TDW_SEED_PROJECT_TITLE  project title (default: "Getting Started — Sample").
  TDW_SEED_PROJECT_ALWAYS '1' to seed whenever the org has zero projects even on
                          later boots (default: same as default behavior — it
                          only seeds when the org has no projects, which already
                          makes it reappear if everything was deleted).

Usage:
    python label_studio/manage.py tdw_seed_project
"""
import os

from django.core.management.base import BaseCommand

SAMPLE_LABEL_CONFIG = """
<View>
  <Text name="text" value="$text"/>
  <Header value="Which sentiment best describes this text?"/>
  <Choices name="sentiment" toName="text" choice="single" showInLine="true">
    <Choice value="Positive"/>
    <Choice value="Neutral"/>
    <Choice value="Negative"/>
  </Choices>
</View>
""".strip()

SAMPLE_TASKS = [
    {'text': 'Label Studio makes it easy to annotate data for machine learning.'},
    {'text': 'The onboarding was confusing and I could not find the export button.'},
    {'text': 'It works. Nothing special, nothing terrible.'},
]


def _truthy(v, default=True):
    if v is None:
        return default
    return str(v).strip().lower() not in ('0', 'false', 'no', 'off', '')


class Command(BaseCommand):
    help = 'Seed a default demo project when the organization has none (idempotent).'

    def handle(self, *args, **options):
        if not _truthy(os.environ.get('TDW_SEED_PROJECT'), default=True):
            self.stdout.write('TDW_SEED_PROJECT disabled; skipping.')
            return

        from organizations.models import Organization
        from projects.models import Project

        org = Organization.objects.first()
        if org is None:
            self.stdout.write('No organization yet; skipping project seed (users seed runs first).')
            return

        if Project.objects.filter(organization=org).exists():
            self.stdout.write('Organization already has project(s); nothing to seed.')
            return

        # Prefer an owner as created_by; fall back to the org creator / any member.
        created_by = getattr(org, 'created_by', None)
        try:
            from organizations.models import OrganizationMember

            owner_member = (
                OrganizationMember.objects.filter(organization=org, role='owner')
                .select_related('user')
                .first()
            )
            if owner_member is not None:
                created_by = owner_member.user
        except Exception:
            pass

        title = os.environ.get('TDW_SEED_PROJECT_TITLE', 'Getting Started — Sample')
        project = Project.objects.create(
            title=title,
            description='A sample text-classification project to get you started. '
            'Edit or delete it any time.',
            organization=org,
            created_by=created_by,
            label_config=SAMPLE_LABEL_CONFIG,
            is_published=True,
        )

        # Add a few example tasks so "Label All Tasks" works immediately.
        try:
            from tasks.models import Task

            tasks = Task.objects.bulk_create([Task(project=project, data=d) for d in SAMPLE_TASKS])
            # keep the project's task counters consistent
            try:
                task_ids = [t.id for t in Task.objects.filter(project=project)]
                project._update_tasks_counters_and_is_labeled(task_ids)
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover - tasks are a nice-to-have
            self.stderr.write(f'seeded project but could not add sample tasks: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Seeded default project "{title}" (id={project.id}) in org {org.id}.'))
