"""Roles: one table says who may do what."""

import pytest

from reqtool import permissions as perm


def test_roles_are_ordered():
    assert perm.role_rank("viewer") < perm.role_rank("editor") < perm.role_rank("admin")
    assert perm.role_rank("nobody") < perm.role_rank("viewer")


def test_what_each_role_may_do():
    assert perm.permissions_for("viewer") == ["read"]
    assert perm.permissions_for("editor") == ["read", "write", "override_rules"]
    assert set(perm.permissions_for("admin")) == set(perm.ACTIONS)
    assert perm.permissions_for(None) == []


@pytest.mark.parametrize("method,path,action", [
    ("DELETE", "/requirements/abc", "delete"),
    ("DELETE", "/principles/abc", "delete"),
    ("DELETE", "/decisions/abc", "delete"),
    ("DELETE", "/tbds/abc", "delete"),
    ("DELETE", "/iterations/i1", "delete"),
    ("PUT", "/workflow", "manage_workflow"),
    ("POST", "/workflows", "manage_workflow"),
    ("POST", "/workflows/preview", "manage_workflow"),
    ("PUT", "/workflows/sprint", "manage_workflow"),
    ("DELETE", "/workflows/sprint", "manage_workflow"),
    ("PUT", "/hierarchy/types/story/workflow", "manage_workflow"),
    ("PUT", "/lint/config", "manage_lint"),
    ("PUT", "/config", "manage_config"),
    ("PUT", "/enums/repo", "manage_config"),
    ("PUT", "/custom-fields", "manage_config"),
    ("POST", "/repo/init", "manage_repo"),
    ("POST", "/repo/switch", "manage_repo"),
    ("POST", "/changesets/switch", "manage_repo"),
    ("POST", "/baselines", "manage_modules"),
    ("POST", "/modules", "manage_modules"),
    ("POST", "/modules/m1/fetch-remote", "manage_modules"),
    ("POST", "/products", "manage_modules"),
    ("POST", "/products/p1/modules", "manage_modules"),
    ("POST", "/webhooks", "manage_webhooks"),
    ("DELETE", "/webhooks/0", "manage_webhooks"),
    ("POST", "/auth/users", "manage_users"),
])
def test_advanced_requests_need_their_action(method, path, action):
    assert perm.required_action(method, path) == action


@pytest.mark.parametrize("method,path", [
    ("GET", "/requirements"), ("POST", "/requirements"), ("PUT", "/requirements/abc"),
    ("POST", "/requirements/abc/transition"), ("POST", "/requirements/abc/approve"),
    ("DELETE", "/requirements/abc/ac/x"), ("POST", "/requirements/abc/comments"),
    ("DELETE", "/requirements/abc/attachments/f.png"), ("POST", "/import/csv"), ("POST", "/iterations"),
    ("POST", "/requirements/bulk"), ("POST", "/requirements/abc/commit"), ("GET", "/workflows"),
    ("GET", "/lint/config"), ("POST", "/lint/text"), ("GET", "/modules"), ("POST", "/principles"),
])
def test_everyday_data_work_needs_only_the_editor_role(method, path):
    assert perm.required_action(method, path) is None


def test_can_uses_the_lowest_role_in_the_table():
    assert perm.can("editor", "write") and not perm.can("viewer", "write")
    assert perm.can("admin", "delete") and not perm.can("editor", "delete")
    assert not perm.can("admin", "no_such_action")
