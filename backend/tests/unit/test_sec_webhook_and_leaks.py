"""SEC-01 et SEC-02 : webhook non authentifié, et fuite d'exception au client.

SEC-01 — la vérification du secret Telegram était conditionnée à son existence :
`if settings.TELEGRAM_WEBHOOK_SECRET:`. Un bot actif sans secret configuré laissait
donc le webhook ouvert à quiconque, c'est-à-dire précisément dans le cas où la
protection compte le plus. Le défaut se désactivait tout seul.

SEC-02 — le statut d'un import raté stockait `f"{type(e).__name__}: {e}"`, renvoyé
tel quel par `GET /import-status/{task_id}`. Un message d'exception expose des
chemins, des fragments de requête et des noms de classes internes.

Tests statiques : ces chemins ne sont atteints ni par la suite d'intégration ni par
un test d'exécution — un webhook non authentifié ne lève aucune erreur, il répond
simplement 200 à un inconnu.
"""

from pathlib import Path

_TELEGRAM = Path(__file__).resolve().parents[2] / "app" / "domains" / "notifications" / "telegram"
_WEBHOOK = (_TELEGRAM / "webhook.py").read_text(encoding="utf-8")
_BACKGROUND = (Path(__file__).resolve().parents[2] / "app" / "domains" / "exchanges" / "background.py").read_text(
    encoding="utf-8"
)


class TestWebhookTelegram:
    def test_l_absence_de_secret_ferme_le_webhook(self):
        assert "if not settings.TELEGRAM_WEBHOOK_SECRET:" in _WEBHOOK, (
            "sans secret, le webhook doit refuser — pas ignorer la vérification"
        )

    def test_le_refus_precede_tout_traitement(self):
        # Le contrôle doit venir avant la lecture du corps de la requête.
        pos_refus = _WEBHOOK.index("if not settings.TELEGRAM_WEBHOOK_SECRET:")
        pos_corps = _WEBHOOK.index("await request.json()")
        assert pos_refus < pos_corps

    def test_la_verification_reste_a_temps_constant(self):
        # `==` révèle le jeton octet par octet via la latence de réponse.
        assert "hmac.compare_digest" in _WEBHOOK
        assert "== settings.TELEGRAM_WEBHOOK_SECRET" not in _WEBHOOK

    def test_l_absence_de_secret_est_journalisee(self):
        # Sans trace, une configuration incomplète se traduit par un bot muet
        # dont personne ne comprend la cause.
        bloc = _WEBHOOK.split("if not settings.TELEGRAM_WEBHOOK_SECRET:")[1][:400]
        assert "logger.error" in bloc


class TestPasDeFuiteAuClient:
    def test_un_echec_ne_rend_au_client_qu_un_libelle_generique(self):
        assert "FAILURE_MESSAGE" in _BACKGROUND and "str(exc)" not in _BACKGROUND, (
            "le détail de l'exception ne doit pas atterrir dans un statut consultable par le client"
        )

    def test_le_detail_reste_journalise_cote_serveur(self):
        assert "logger.exception(" in _BACKGROUND
