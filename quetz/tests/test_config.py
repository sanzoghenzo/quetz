import os

import pytest

from quetz.config import Config, ConfigEntry, ConfigSection
from quetz.dao import Dao
from quetz.errors import ConfigError


@pytest.fixture
def config_extra():
    return r"""[users]
admins=["bartosz"]
default_role = "member"
create_default_channel = true
"""


def test_config_users(config):
    assert config.users_default_role == "member"
    assert config.users_create_default_channel
    assert config.users_admins == ["bartosz"]
    assert not config.users_maintainers
    assert not config.users_members


@pytest.mark.parametrize(
    "config_extra", ["[users]\nadmins=[]", "[users]\nmaintainers=[]"]
)
def test_config_empty_users_section(dao: Dao, user, config):

    assert config.configured_section("users")
    assert not config.users_admins
    assert not config.users_maintainers
    assert not config.users_members
    assert not config.users_default_role
    assert not config.users_create_default_channel


def test_config_is_singleton(config):

    c = Config()

    assert c is config

    Config._instances = {}

    c_new = Config()

    assert c_new is not config

    c_file = Config("config.toml")

    assert c_file is c_new


def test_config_with_path(config_dir, config_base):

    one_path = os.path.join(config_dir, "one_config.toml")
    other_path = os.path.join(config_dir, "other_config.toml")
    with open(one_path, 'w') as fid:
        fid.write("\n".join([config_base, "[users]\nadmins=['one']"]))
    with open(other_path, 'w') as fid:
        fid.write("\n".join([config_base, "[users]\nadmins=['other']"]))

    Config._instances = {}

    c_one = Config(one_path)

    assert c_one.configured_section("users")
    assert c_one.users_admins == ["one"]

    c_other = Config(other_path)

    assert c_other.configured_section("users")
    assert c_other.users_admins == ["other"]

    c_new = Config(one_path)

    assert c_new is c_one


def test_config_extend_require(config):
    with pytest.raises(ConfigError):
        config.register(
            [
                ConfigSection(
                    "other_plugin",
                    [
                        ConfigEntry("some_config_value", str),
                    ],
                )
            ]
        )
    # remove last entry again
    config._config_map.pop()


@pytest.mark.parametrize(
    "config_extra", ["[extra_plugin]\nsome=\"testvalue\"\nconfig=\"othervalue\"\n"]
)
def test_config_extend(config):
    config.register(
        [
            ConfigSection(
                "extra_plugin",
                [
                    ConfigEntry("some", str),
                    ConfigEntry("config", str),
                    ConfigEntry("has_default", str, "iamdefault"),
                ],
            )
        ]
    )

    assert config.extra_plugin_some == 'testvalue'
    assert config.extra_plugin_config == 'othervalue'
    assert config.extra_plugin_has_default == 'iamdefault'

    config._config_map.pop()
