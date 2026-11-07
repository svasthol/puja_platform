from scripts.staging_db_tunnel import staging_url_via_tunnel


def test_rewrite_public_ip_to_tunnel_port():
    url = "postgresql://puja_migrate:secret@140.245.245.201:5432/Mana_Guruji"
    out = staging_url_via_tunnel(url, local_port=15432, rewrite_remote=True)
    assert "@127.0.0.1:15432/" in out
    assert "140.245.245.201" not in out


def test_keep_tunnel_url_unchanged():
    url = "postgresql://puja_migrate:secret@127.0.0.1:15432/Mana_Guruji"
    assert staging_url_via_tunnel(url, local_port=15432) == url
