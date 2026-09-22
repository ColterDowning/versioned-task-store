# OSWorld desktop integration test

Use a Python environment with the full OSWorld-V2 checkout and its dependencies
installed at commit `12083cf1ad95d19875c1eedb77cf59e9408b939e`, plus pytest.
The two-file upstream fixture used by the local test is not sufficient.

The default provider is Docker, running OSWorld's Ubuntu VM with KVM acceleration.
It requires Docker access, `/dev/kvm`, the `happysixd/osworld-docker` runtime
image, and an extracted Ubuntu `.qcow2` image. The release manifest pins that
image to `xlangai/v2-image@v2026.06.24`:

- Archive: `osworld-v2-ubuntu-x86.qcow2.zip`
- SHA-256: `eb737ae70b49849e24af407de6a518439a23de05a8497096a948334ce0a909aa`

On 2026-09-24, the `v2026.06.24` asset tag did not match the release manifest's
checksum. The matching archive is available at dataset commit
`6e16459a2feb5a8f1ed65babcfe7a2a6205d049d` under
`osworld-v2-ubuntu-x86.before-20260716T053042Z-repo-update.qcow2.zip`.
Verify the checksum above when provisioning rather than trusting the tag alone.

The test uploads input.txt and writes result.txt under `/home/user` in the
test desktop, then stops and removes its container during cleanup.

Run this test in a separate pytest process from the local compatibility test,
which imports a lightweight desktop_env package. From the task-store repository
root, set `OSWORLD_CHECKOUT` to your full OSWorld checkout. It can be a relative
or absolute path; the example assumes the repositories are siblings:

```bash
OSWORLD_CHECKOUT="../OSWorld-V2"  # Change this to your checkout location.
OSWORLD_ROOT="$(cd "$OSWORLD_CHECKOUT" && pwd)"
OSWORLD_IMAGE="$OSWORLD_ROOT/docker_vm_data/osworld-v2-ubuntu-x86.qcow2"
# Change OSWORLD_IMAGE if you extracted the verified image somewhere else.

RUN_OSWORLD_INTEGRATION=1 \
OSWORLD_TEST_VM_PATH="$OSWORLD_IMAGE" \
PYTHONPATH="$OSWORLD_ROOT" \
"$OSWORLD_ROOT/.venv/bin/python" -B -m pytest -q tests/test_osworld_integration.py
```

Use the Python interpreter from the full OSWorld environment. For VMware instead,
set `OSWORLD_TEST_PROVIDER=vmware` and supply a `.vmx` path with an `init_state`
snapshot.

Without the opt-in variable, the test is skipped. When enabled, missing
prerequisites cause failure rather than a passing or skipped integration result.
The task resolves assets relative to its exported Python file; it needs no
`OSWORLD_FILE_BASE_URL`. No agent or model API is used.

## Python environment and Docker runtime

With Git, uv, Docker, and KVM available on a Linux host, prepare a checkout at a
location of your choice. If you don't already have one, the sibling layout above
can be created from the task-store repository root with:

```bash
git clone https://github.com/xlang-ai/OSWorld-V2.git ../OSWorld-V2
git -C ../OSWorld-V2 checkout --detach 12083cf1ad95d19875c1eedb77cf59e9408b939e
```

Inside the pinned OSWorld checkout, install its dependencies and pytest:

```bash
uv sync --frozen
uv pip install --python .venv/bin/python pytest
```

Download, verify, and extract the image described above, then set `OSWORLD_IMAGE`
to its extracted `.qcow2` file. The archive is approximately 14 GB and the
extracted image is approximately 27 GB.

To use the Docker runtime from the verified run:

```bash
OSWORLD_RUNTIME="happysixd/osworld-docker@sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
docker pull "$OSWORLD_RUNTIME"
docker tag "$OSWORLD_RUNTIME" happysixd/osworld-docker:latest
```

Upstream starts the locally tagged `happysixd/osworld-docker:latest`. The tag
command selects the pinned runtime; pulling `latest` again can change it.

Verified on 2026-09-24: the integration test passed against the real desktop,
including asset upload and scores of 0.0 and 1.0 for known outputs. Cleanup
removed the test container. No model API or cloud provider was used.
