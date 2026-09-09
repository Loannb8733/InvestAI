"""Filet sur la signature des requêtes vers les exchanges.

Une signature fausse ne casse rien de visible : l'exchange répond « unauthorized »,
le connecteur avale l'exception et rend une liste vide. Le portefeuille paraît
simplement… vide. C'est le mode de panne le plus discret de toute la
synchronisation, et il n'était couvert nulle part — Binance 20 %, Bybit 16 %,
Crypto.com 16 %.

Ne sont épinglés ici que les trois exchanges réellement branchés sur des clés
(Binance : 19 actifs, Crypto.com : 10, Bybit : 2). Chaque schéma de signature est
recalculé à la main dans le test, à partir de la documentation de l'exchange :
comparer la fonction à elle-même ne prouverait rien.
"""

import hashlib
import hmac
import itertools
from urllib.parse import urlencode

import pytest

from app.services.exchanges.binance import BinanceService
from app.services.exchanges.bybit import BybitService
from app.services.exchanges.cryptocom import CryptoComService

CLE = "cle-publique-de-test"
SECRET = "secret-de-test"


def hmac_sha256(message: str) -> str:
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


class ClientQuiRetient:
    """Faux client HTTP : retient le corps envoyé au lieu de le transmettre."""

    class _Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0, "result": {"accounts": []}}

    def __init__(self, corps: dict):
        self._corps = corps

    async def post(self, url, json):
        self._corps.update(json)
        return self._Reponse()


class TestBinance:
    @pytest.fixture
    def service(self):
        return BinanceService(CLE, SECRET)

    def test_la_signature_couvre_toute_la_chaine_de_requete(self, service):
        """Binance signe la query string complète, horodatage et fenêtre compris.

        Recalculée ici depuis le dict rendu, donc à partir de ce que le
        connecteur enverra réellement — et non depuis les paramètres d'entrée,
        qui n'en sont qu'une partie.
        """
        signes = service._sign_request({"symbol": "BTCEUR"})

        signature = signes.pop("signature")
        assert signature == hmac_sha256(urlencode(signes))

    def test_l_horodatage_et_la_fenetre_sont_ajoutes(self, service):
        signes = service._sign_request({"symbol": "BTCEUR"})

        assert signes["recvWindow"] == 60000
        assert isinstance(signes["timestamp"], int)

    def test_la_signature_est_placee_en_dernier(self, service):
        """L'ordre compte : Binance rejette une query dont `signature`
        n'est pas le dernier paramètre."""
        signes = service._sign_request({"symbol": "BTCEUR"})

        assert list(signes)[-1] == "signature"

    def test_le_decalage_d_horloge_du_serveur_est_applique(self, service):
        """Contre l'erreur -1021 (« timestamp ahead of server time »).

        Binance refuse une requête dont l'horodatage s'écarte de son horloge.
        Le connecteur mesure une fois le décalage et le reporte sur chaque
        requête ; un décalage d'une heure doit se voir dans l'horodatage.
        """
        sans_decalage = service._sign_request({})["timestamp"]
        service._server_time_offset = 3_600_000

        avec_decalage = service._sign_request({})["timestamp"]

        assert avec_decalage - sans_decalage == pytest.approx(3_600_000, abs=1000)

    def test_deux_secrets_distincts_donnent_deux_signatures(self, service):
        autre = BinanceService(CLE, "un-autre-secret")
        params = {"symbol": "BTCEUR", "timestamp": 1, "recvWindow": 60000}

        # Même chaîne signée de part et d'autre : seul le secret diffère.
        assert service._sign_request(dict(params))["signature"] != autre._sign_request(dict(params))["signature"]

    def test_l_entete_porte_la_cle_publique(self, service):
        assert service._get_headers() == {"X-MBX-APIKEY": CLE}


class TestBybit:
    @pytest.fixture
    def service(self):
        return BybitService(CLE, SECRET)

    def test_la_signature_suit_le_schema_v5(self, service):
        """Bybit v5 signe `timestamp + clé + recvWindow + query`, concaténés
        sans séparateur — et non la query seule comme Binance."""
        signature = service._sign_request("1700000000000", {"category": "spot"})

        assert signature == hmac_sha256("1700000000000" + CLE + "5000" + "category=spot")

    def test_une_requete_sans_parametre_signe_une_query_vide(self, service):
        signature = service._sign_request("1700000000000", {})

        assert signature == hmac_sha256("1700000000000" + CLE + "5000")

    def test_l_horodatage_entre_dans_la_signature(self, service):
        # Deux horodatages voisins : si l'un des deux était ignoré, les
        # signatures seraient identiques.
        params = {"category": "spot"}

        assert service._sign_request("1700000000000", params) != service._sign_request("1700000000001", params)

    def test_les_entetes_portent_la_signature_du_meme_horodatage(self, service):
        """L'en-tête `X-BAPI-TIMESTAMP` doit être celui qui a été signé.

        S'ils divergeaient, Bybit recalculerait la signature sur l'horodatage
        reçu et la trouverait fausse — la panne silencieuse.
        """
        entetes = service._get_headers("1700000000000", {"category": "spot"})

        assert entetes["X-BAPI-TIMESTAMP"] == "1700000000000"
        assert entetes["X-BAPI-SIGN"] == service._sign_request(entetes["X-BAPI-TIMESTAMP"], {"category": "spot"})
        assert entetes["X-BAPI-API-KEY"] == CLE
        assert entetes["X-BAPI-RECV-WINDOW"] == "5000"

    def test_l_url_par_defaut_est_le_domaine_global(self, service):
        """Bybit a deux domaines ; l'européen ne sert qu'en repli."""
        assert service.BASE_URL == "https://api.bybit.com"

        service._base_url = "https://api.bybit.nl"

        assert service.BASE_URL == "https://api.bybit.nl"


class TestCryptoCom:
    @pytest.fixture
    def service(self):
        return CryptoComService(CLE, SECRET)

    def test_les_parametres_sont_concatenes_dans_l_ordre_alphabetique(self, service):
        """Crypto.com signe `méthode + id + clé + paramètres + nonce`.

        Les paramètres sont aplatis en `clé1valeur1clé2valeur2…`, triés par nom
        — l'ordre du dict d'appel ne doit donc rien changer.
        """
        signature = service._sign_request(
            "private/get-trades", "42", {"page": 0, "instrument_name": "BTC_USDT"}, "1700000000000"
        )

        attendu = "private/get-trades" + "42" + CLE + "instrument_nameBTC_USDTpage0" + "1700000000000"
        assert signature == hmac_sha256(attendu)

    def test_l_ordre_du_dict_d_appel_est_indifferent(self, service):
        premier = service._sign_request("m", "1", {"a": 1, "b": 2}, "1700000000000")
        second = service._sign_request("m", "1", {"b": 2, "a": 1}, "1700000000000")

        assert premier == second

    def test_une_requete_sans_parametre_ne_signe_rien_entre_la_cle_et_le_nonce(self, service):
        signature = service._sign_request("private/get-account-summary", "42", {}, "1700000000000")

        assert signature == hmac_sha256("private/get-account-summary" + "42" + CLE + "1700000000000")

    def test_l_identifiant_de_requete_entre_dans_la_signature(self, service):
        assert service._sign_request("m", "1", {}, "1") != service._sign_request("m", "2", {}, "1")

    def test_le_nonce_entre_dans_la_signature(self, service):
        assert service._sign_request("m", "1", {}, "1") != service._sign_request("m", "1", {}, "2")

    async def test_le_nonce_signe_est_celui_qui_est_envoye(self, service, monkeypatch):
        """Le défaut : la signature portait un nonce que le serveur ne voyait pas.

        Le nonce était lu deux fois à l'horloge — une fois pour le corps de la
        requête, une fois dans la signature. Crypto.com recalcule la signature
        à partir du nonce qu'il reçoit : dès qu'une frontière de milliseconde
        tombait entre les deux lectures, les deux ne concordaient plus et la
        requête était refusée. Le connecteur avale l'erreur et rend une liste
        vide — le portefeuille Crypto.com paraissait simplement vide.

        L'horloge avance ici d'une milliseconde à chaque lecture, ce qui rend le
        cas systématique au lieu d'occasionnel.
        """
        millisecondes = itertools.count(1_700_000_000_000)
        monkeypatch.setattr("app.services.exchanges.cryptocom.time.time", lambda: next(millisecondes) / 1000.0)
        envoye = {}
        monkeypatch.setattr(CryptoComService, "_get_client", classmethod(lambda cls: ClientQuiRetient(envoye)))

        await service._make_request("private/get-account-summary", {})

        assert envoye["sig"] == service._sign_request(envoye["method"], envoye["id"], {}, envoye["nonce"])

    async def test_l_identifiant_et_le_nonce_restent_distincts_du_corps(self, service, monkeypatch):
        # Garde-fou sur le corps lui-même : les quatre champs que Crypto.com
        # relit pour vérifier la signature doivent tous y figurer.
        envoye = {}
        monkeypatch.setattr(CryptoComService, "_get_client", classmethod(lambda cls: ClientQuiRetient(envoye)))

        await service._make_request("private/get-account-summary", {})

        assert set(envoye) == {"id", "method", "api_key", "params", "sig", "nonce"}
        assert envoye["api_key"] == CLE
