"""Tests for the direnv helper module (HMB-S010)."""

from __future__ import annotations

_START = "# --- himitsubako start ---"
_END = "# --- himitsubako end ---"


class TestGenerateEnvrc:
    def test_contains_start_and_end_markers(self):
        from himitsubako.direnv import generate_envrc

        content = generate_envrc(secrets_file=".secrets.enc.yaml")
        assert _START in content
        assert _END in content

    def test_uses_sops_decrypt_command(self):
        from himitsubako.direnv import generate_envrc

        content = generate_envrc(secrets_file=".secrets.enc.yaml")
        assert "sops -d" in content
        assert ".secrets.enc.yaml" in content

    def test_dotenv_output_type(self):
        from himitsubako.direnv import generate_envrc

        content = generate_envrc(secrets_file=".secrets.enc.yaml")
        # We rely on sops's native dotenv output type so we don't need yq.
        assert "--output-type dotenv" in content


class TestUpdateEnvrc:
    def test_creates_envrc_when_absent(self, tmp_path):
        from himitsubako.direnv import update_envrc

        envrc = tmp_path / ".envrc"
        update_envrc(envrc, secrets_file=".secrets.enc.yaml")

        assert envrc.exists()
        content = envrc.read_text()
        assert _START in content

    def test_preserves_user_lines_outside_managed_block(self, tmp_path):
        from himitsubako.direnv import update_envrc

        envrc = tmp_path / ".envrc"
        envrc.write_text(
            "# my custom hook\nexport MY_VAR=hello\nuse flake\n"
        )
        update_envrc(envrc, secrets_file=".secrets.enc.yaml")

        content = envrc.read_text()
        assert "# my custom hook" in content
        assert "export MY_VAR=hello" in content
        assert "use flake" in content
        assert _START in content
        assert _END in content

    def test_replaces_existing_managed_block(self, tmp_path):
        from himitsubako.direnv import update_envrc

        envrc = tmp_path / ".envrc"
        envrc.write_text(
            f"user_pre_line\n{_START}\nstale_line_to_replace\n{_END}\nuser_post_line\n"
        )
        update_envrc(envrc, secrets_file="newpath.enc.yaml")

        content = envrc.read_text()
        assert "user_pre_line" in content
        assert "user_post_line" in content
        assert "stale_line_to_replace" not in content
        assert "newpath.enc.yaml" in content
        # Only one start marker (no duplication)
        assert content.count(_START) == 1
        assert content.count(_END) == 1

    def test_idempotent(self, tmp_path):
        from himitsubako.direnv import update_envrc

        envrc = tmp_path / ".envrc"
        update_envrc(envrc, secrets_file=".secrets.enc.yaml")
        first = envrc.read_text()
        update_envrc(envrc, secrets_file=".secrets.enc.yaml")
        second = envrc.read_text()
        assert first == second
