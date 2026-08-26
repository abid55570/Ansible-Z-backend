"""Day-2 operations layer.

Every generated project (template-based or custom IR design) provisions
infrastructure with ``site.yml``. The Day-2 layer adds the *operate* half:
a data-driven way to deploy applications onto that infrastructure and to ship
new versions or roll back — without the user hand-writing any Ansible.

``day2_files()`` returns a small, self-contained bundle that is merged into
every export:

* ``apps.yml``     — the only file a user edits: declare apps, bump a tag to update.
* ``deploy.yml``   — rolling deploy/update of every app in ``apps.yml``.
* ``rollback.yml`` — redeploy every app at its ``rollback_tag``.
* ``DAY2.md``      — how the workflow fits together.

The playbooks target container workloads (the common case for "add another
app") via ``community.docker`` and pass ``ansible-playbook --syntax-check``.
"""

from app.services.projectfmt import normalize_files

APPS_MANIFEST = """---
# ============================================================================
# Day-2 application manifest
# ----------------------------------------------------------------------------
# This is the ONE file you edit to run apps on your provisioned infrastructure.
#
#   ansible-playbook deploy.yml      # deploy apps / roll out a new version
#   ansible-playbook rollback.yml    # roll every app back to its rollback_tag
#
# Ship a NEW version of an app : bump its `tag`, then re-run deploy.yml.
# Add a NEW app                : append another entry under `apps:`, run deploy.yml.
# ============================================================================

# Inventory group your application servers belong to. The dynamic inventory
# groups instances tagged Role=app as "role_app".
app_host_group: role_app

# Roll the update out to this many hosts at a time: "1", "25%", "100%", ...
deploy_batch: "100%"

# Optional private registry. Leave registry_url empty ("") to skip the login.
registry_url: ""
registry_username: ""
registry_password: ""

apps:
  - name: web
    image: nginx          # repository (may include a registry host)
    tag: "1.27"           # bump this and re-run deploy.yml to update
    rollback_tag: "1.26"  # rollback.yml redeploys this tag
    port: 8080            # host port to publish
    container_port: 80    # port the app listens on inside the container
    health_path: /        # GET this path; deploy waits until it returns 200
    env:
      APP_ENV: production
"""

DEPLOY_PLAYBOOK = """---
# Day-2: deploy or update every application declared in apps.yml.
#   ansible-playbook deploy.yml
- name: Deploy applications
  hosts: "{{ app_host_group | default('role_app') }}"
  become: true
  serial: "{{ deploy_batch | default('100%') }}"
  vars_files:
    - apps.yml
  tasks:
    - name: Ensure the container runtime is running
      ansible.builtin.service:
        name: docker
        state: started
        enabled: true

    - name: Log in to the container registry
      community.docker.docker_login:
        registry_url: "{{ registry_url }}"
        username: "{{ registry_username }}"
        password: "{{ registry_password }}"
      no_log: true
      when: registry_url | default('') | length > 0

    - name: Pull the pinned image for each application
      community.docker.docker_image:
        name: "{{ item.image }}"
        tag: "{{ item.tag | default('latest') }}"
        source: pull
        force_source: true
      loop: "{{ apps }}"
      loop_control:
        label: "{{ item.name }}:{{ item.tag | default('latest') }}"

    - name: Deploy or update each application container
      community.docker.docker_container:
        name: "{{ item.name }}"
        image: "{{ item.image }}:{{ item.tag | default('latest') }}"
        state: started
        recreate: true
        restart_policy: unless-stopped
        published_ports:
          - "{{ item.port }}:{{ item.container_port | default(item.port) }}"
        env: "{{ item.env | default({}) }}"
      loop: "{{ apps }}"
      loop_control:
        label: "{{ item.name }}"

    - name: Wait until each application is healthy
      ansible.builtin.uri:
        url: "http://127.0.0.1:{{ item.port }}{{ item.health_path | default('/') }}"
      register: app_health
      retries: "{{ item.health_retries | default(12) }}"
      delay: "{{ item.health_delay | default(5) }}"
      until: app_health.status == 200
      loop: "{{ apps }}"
      loop_control:
        label: "{{ item.name }}"
      when: item.health_path | default('/') | length > 0
"""

ROLLBACK_PLAYBOOK = """---
# Day-2: roll every application back to its rollback_tag image.
#   ansible-playbook rollback.yml
- name: Roll back applications
  hosts: "{{ app_host_group | default('role_app') }}"
  become: true
  vars_files:
    - apps.yml
  tasks:
    - name: Pull the rollback image for each application
      community.docker.docker_image:
        name: "{{ item.image }}"
        tag: "{{ item.rollback_tag | default('previous') }}"
        source: pull
        force_source: true
      loop: "{{ apps }}"
      loop_control:
        label: "{{ item.name }}:{{ item.rollback_tag | default('previous') }}"

    - name: Redeploy each application at its rollback tag
      community.docker.docker_container:
        name: "{{ item.name }}"
        image: "{{ item.image }}:{{ item.rollback_tag | default('previous') }}"
        state: started
        recreate: true
        restart_policy: unless-stopped
        published_ports:
          - "{{ item.port }}:{{ item.container_port | default(item.port) }}"
        env: "{{ item.env | default({}) }}"
      loop: "{{ apps }}"
      loop_control:
        label: "{{ item.name }}"
"""

DAY2_DOC = """# Day-2 operations

`site.yml` builds your infrastructure. These files run **applications** on it
and let you ship updates — no extra Ansible to write.

## One-time

Install the collection these playbooks use:

```bash
ansible-galaxy collection install community.docker
```

Your app servers must be reachable over SSH and have Docker installed, and the
instances that should run apps must be tagged `Role=app` (the dynamic inventory
groups them as `role_app`). Override the target group by editing `app_host_group`
in `apps.yml`. (The `single-vm-app` starter template installs Docker for you via
cloud-init.)

## Deploy / update

1. Edit **`apps.yml`** — declare each app (image, tag, port, health check).
2. Run:

   ```bash
   ansible-playbook deploy.yml
   ```

   For each app this pulls the pinned image, (re)creates the container, and
   waits until `health_path` returns `200`. `deploy_batch` controls how many
   hosts update at once (a rolling update).

**Ship a new version:** bump the app's `tag` in `apps.yml`, re-run `deploy.yml`.

**Add another app:** append an entry under `apps:`, re-run `deploy.yml`.

## Roll back

```bash
ansible-playbook rollback.yml
```

Redeploys every app at its `rollback_tag`.
"""


def day2_files() -> dict[str, str]:
    """Return the Day-2 operations bundle merged into every generated project."""
    return normalize_files({
        "apps.yml": APPS_MANIFEST,
        "deploy.yml": DEPLOY_PLAYBOOK,
        "rollback.yml": ROLLBACK_PLAYBOOK,
        "DAY2.md": DAY2_DOC,
    })
