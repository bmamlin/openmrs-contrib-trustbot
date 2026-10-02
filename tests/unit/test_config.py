from pathlib import Path

import yaml

from src.config import load_config

EXAMPLE_CONFIG = Path(__file__).parents[2] / "config" / "config.example.yaml"


def test_load_config_parses_example_file():
    config = load_config(EXAMPLE_CONFIG)

    assert config.keycloak.realm == "OpenMRS"
    assert config.database.path == "/data/audit.db"
    assert config.discourse.webhook.workflow_name == "trusted"


def test_dry_run_defaults_to_false_when_absent(tmp_path):
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw.pop("dry_run", None)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw))

    config = load_config(config_path)

    assert config.dry_run is False


def test_dry_run_parses_true_when_set(tmp_path):
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw["dry_run"] = True
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw))

    config = load_config(config_path)

    assert config.dry_run is True


def test_load_config_uses_config_path_env_var(monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(EXAMPLE_CONFIG))

    config = load_config()

    assert config.keycloak.realm == "OpenMRS"
