import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import ObjectDeletedError

from quetz import errors, rest_models
from quetz.dao import Dao
from quetz.database import get_session
from quetz.db_models import Channel, Package, PackageVersion


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


@pytest.fixture
def channel(dao, db, user, channel_name):

    channel_data = rest_models.Channel(name=channel_name, private=False)
    channel = dao.create_channel(channel_data, user.id, "owner")
    yield channel

    try:
        db.delete(channel)
        db.commit()
    except ObjectDeletedError:
        pass


@pytest.fixture
def package(dao, channel, package_name, user, db):
    package_data = rest_models.Package(name=package_name)

    package = dao.create_package(channel.name, package_data, user.id, "owner")

    yield package

    db.delete(package)
    db.commit()


def test_create_version(dao, package, channel_name, package_name, db, user):

    assert (
        not db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )
    assert dao.db == db
    dao.create_version(
        channel_name=channel_name,
        package_name=package_name,
        package_format="tarbz2",
        platform="noarch",
        version="0.0.1",
        build_number="0",
        build_string="",
        filename="filename.tar.bz2",
        info="{}",
        uploader_id=user.id,
        upsert=False,
    )

    created_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )

    assert created_version
    assert created_version.version == "0.0.1"
    assert created_version.build_number == 0
    assert created_version.filename == "filename.tar.bz2"
    assert created_version.info == "{}"
    assert created_version.time_created == created_version.time_modified

    # error for insert-only with existing row
    with pytest.raises(IntegrityError):
        dao.create_version(
            channel_name=channel_name,
            package_name=package_name,
            package_format="tarbz2",
            platform="noarch",
            version="0.0.1",
            build_number="0",
            build_string="",
            filename="filename-2.tar.bz2",
            info="{}",
            uploader_id=user.id,
            upsert=False,
        )

    # update with upsert
    dao.create_version(
        channel_name=channel_name,
        package_name=package_name,
        package_format="tarbz2",
        platform="noarch",
        version="0.0.1",
        build_number="0",
        build_string="",
        filename="filename-2.tar.bz2",
        info='{"version": "x.y.z"}',
        uploader_id=user.id,
        upsert=True,
    )

    created_version = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_name == package_name)
        .first()
    )

    assert created_version
    assert created_version.version == "0.0.1"
    assert created_version.build_number == 0
    assert created_version.filename == "filename-2.tar.bz2"
    assert created_version.info == '{"version": "x.y.z"}'
    assert created_version.time_created != created_version.time_modified


def test_update_channel(dao, channel, db):

    assert not channel.private
    dao.update_channel(channel.name, {"private": True})

    channel = db.query(Channel).filter(Channel.name == channel.name).one()

    assert channel.private


def test_create_user_with_profile(dao: Dao, user_without_profile):

    user = dao.create_user_with_profile(
        user_without_profile.username,
        provider="github",
        identity_id="1",
        name="new user",
        avatar_url="http://avatar",
        role=None,
        exist_ok=True,
    )

    assert user.profile

    with pytest.raises(IntegrityError):
        dao.create_user_with_profile(
            user_without_profile.username,
            provider="github",
            identity_id="1",
            name="new user",
            avatar_url="http://avatar",
            role=None,
            exist_ok=False,
        )


@pytest.fixture
def db_extra(database_url):
    """a separate session for db connection

    Use only for tests that require two sessions concurrently.
    For most cases you will want to use the db fixture (from quetz.testing.fixtures)"""

    session = get_session(database_url)

    yield session

    session.close()


@pytest.fixture
def dao_extra(db_extra):

    return Dao(db_extra)


@pytest.fixture
def user_with_channel(dao, db):
    channel_data = rest_models.Channel(name="new-test-channel", private=False)

    user = dao.create_user_with_role("new-user")
    user_id = user.id
    channel = dao.create_channel(channel_data, user_id, "owner")
    db.commit()

    yield user_id
    db.delete(channel)
    db.delete(user)
    db.commit()


# disable running tests in transaction and use on disk database
# because we want to connect to the db with two different
# client concurrently
@pytest.mark.parametrize("sqlite_in_memory", [False])
@pytest.mark.parametrize("auto_rollback", [False])
def test_rollback_on_collision(dao: Dao, db, dao_extra, user_with_channel):
    """testing rollback on concurrent writes."""

    new_package = rest_models.Package(name=f"new-package-{uuid.uuid4()}")

    user_id = user_with_channel
    channel_name = "new-test-channel"

    dao.create_package(channel_name, new_package, user_id, "owner")
    with pytest.raises(errors.DBError, match="(IntegrityError)|(UniqueViolation)"):
        dao_extra.create_package(channel_name, new_package, user_id, "owner")

    requested = db.query(Package).filter(Package.name == new_package.name).one_or_none()

    assert requested

    # need to clean up because we didn't run the test in a transaction

    db.delete(requested)
    db.commit()
