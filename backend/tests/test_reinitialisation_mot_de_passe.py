"""Filet sur la réinitialisation et le changement de mot de passe.

Trois routes sans aucun test — `forgot-password`, `reset-password`,
`change-password` — sur le chemin le plus sensible de l'application : celui par
lequel on reprend la main sur un compte. `endpoints/auth.py` est couvert à
50 %, et ce qui manquait était précisément cette partie-là.

Le filet épingle ce qui protège (jeton imprévisible, à usage unique, expirant,
et refus d'énumérer les comptes) et **ce qui ne protège pas** : deux constats
sont commentés là où ils apparaissent (NEW-65 et NEW-66).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole

MOT_DE_PASSE_VALIDE = "NouveauMotDePasse1!"


@pytest.fixture
async def compte(db_session) -> User:
    utilisateur = User(
        email="titulaire@test.com",
        password_hash=hash_password("AncienMotDePasse1!"),
        role=UserRole.USER,
        first_name="Titulaire",
        last_name="Compte",
    )
    db_session.add(utilisateur)
    await db_session.commit()
    await db_session.refresh(utilisateur)
    return utilisateur


async def _recharger(db_session, compte: User) -> User:
    await db_session.refresh(compte)
    return compte


async def _demander_reinitialisation(client, email: str, monkeypatch):
    """L'envoi d'email est doublé : la route ne doit pas dépendre du courrier."""
    envois = []

    async def _faux_envoi(self, to_email, to_name, subject, body):
        envois.append({"to": to_email, "body": body})

    monkeypatch.setattr("app.services.notification_service.NotificationService._send_email", _faux_envoi)
    reponse = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    return reponse, envois


class TestDemandeDeReinitialisation:
    async def test_un_jeton_est_pose_et_expire_dans_une_heure(self, client, db_session, compte, monkeypatch):
        reponse, _ = await _demander_reinitialisation(client, compte.email, monkeypatch)

        assert reponse.status_code == 200
        compte = await _recharger(db_session, compte)
        assert compte.password_reset_token
        assert len(compte.password_reset_token) >= 40, "un jeton court serait devinable"
        delai = compte.password_reset_expires - datetime.now(timezone.utc)
        assert timedelta(minutes=55) < delai <= timedelta(hours=1)

    async def test_le_lien_envoye_porte_le_jeton(self, client, db_session, compte, monkeypatch):
        _, envois = await _demander_reinitialisation(client, compte.email, monkeypatch)

        compte = await _recharger(db_session, compte)
        assert len(envois) == 1
        assert envois[0]["to"] == compte.email
        assert compte.password_reset_token in envois[0]["body"]

    async def test_une_adresse_inconnue_recoit_la_meme_reponse(self, client, compte, monkeypatch):
        """Le refus d'énumérer : la réponse ne dit pas si le compte existe.

        Une réponse différente transformerait ce formulaire en outil de
        vérification d'adresses — la première étape d'une campagne ciblée.

        La fixture `compte` est indispensable ici : sans elle, les deux adresses
        seraient inconnues et le test passerait quoi que fasse la route.
        """
        connue, _ = await _demander_reinitialisation(client, compte.email, monkeypatch)
        inconnue, envois = await _demander_reinitialisation(client, "personne@test.com", monkeypatch)

        assert inconnue.status_code == connue.status_code == 200
        assert inconnue.json() == connue.json()
        assert envois == [], "aucun email ne part vers une adresse inconnue"

    async def test_un_compte_desactive_ne_recoit_pas_de_lien(self, client, db_session, compte, monkeypatch):
        compte.is_active = False
        await db_session.commit()

        reponse, envois = await _demander_reinitialisation(client, compte.email, monkeypatch)

        assert reponse.status_code == 200
        assert envois == []
        assert (await _recharger(db_session, compte)).password_reset_token is None

    async def test_une_seconde_demande_invalide_le_jeton_precedent(self, client, db_session, compte, monkeypatch):
        # Sans quoi deux liens vivraient en parallèle, dont un que l'utilisateur
        # croit périmé.
        await _demander_reinitialisation(client, compte.email, monkeypatch)
        premier = (await _recharger(db_session, compte)).password_reset_token

        await _demander_reinitialisation(client, compte.email, monkeypatch)

        assert (await _recharger(db_session, compte)).password_reset_token != premier

    async def test_une_panne_d_email_ne_fait_pas_echouer_la_demande(self, client, db_session, compte, monkeypatch):
        """Le jeton est posé avant l'envoi et l'exception est avalée.

        L'utilisateur voit un succès sans recevoir de courrier — le jeton existe
        pourtant bien en base. C'est un choix : ne pas révéler l'état du service
        de messagerie, au prix d'un message trompeur en cas de panne.
        """

        async def _envoi_en_panne(self, **kwargs):
            raise RuntimeError("SMTP indisponible")

        monkeypatch.setattr("app.services.notification_service.NotificationService._send_email", _envoi_en_panne)

        reponse = await client.post("/api/v1/auth/forgot-password", json={"email": compte.email})

        assert reponse.status_code == 200
        assert (await _recharger(db_session, compte)).password_reset_token


class TestReinitialisation:
    async def _jeton(self, client, db_session, compte, monkeypatch) -> str:
        await _demander_reinitialisation(client, compte.email, monkeypatch)
        return (await _recharger(db_session, compte)).password_reset_token

    async def test_le_mot_de_passe_est_remplace_et_le_jeton_consomme(self, client, db_session, compte, monkeypatch):
        jeton = await self._jeton(client, db_session, compte, monkeypatch)

        reponse = await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton, "new_password": MOT_DE_PASSE_VALIDE}
        )

        assert reponse.status_code == 200
        compte = await _recharger(db_session, compte)
        assert compte.password_reset_token is None
        assert compte.password_reset_expires is None
        connexion = await client.post(
            "/api/v1/auth/login", json={"email": compte.email, "password": MOT_DE_PASSE_VALIDE}
        )
        assert connexion.status_code == 200

    async def test_le_jeton_ne_sert_qu_une_fois(self, client, db_session, compte, monkeypatch):
        jeton = await self._jeton(client, db_session, compte, monkeypatch)
        await client.post("/api/v1/auth/reset-password", json={"token": jeton, "new_password": MOT_DE_PASSE_VALIDE})

        second = await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton, "new_password": "EncoreAutreChose1!"}
        )

        assert second.status_code == 400

    async def test_un_jeton_inconnu_est_refuse(self, client):
        reponse = await client.post(
            "/api/v1/auth/reset-password", json={"token": "jeton-invente", "new_password": MOT_DE_PASSE_VALIDE}
        )

        assert reponse.status_code == 400

    async def test_un_jeton_expire_est_refuse_et_efface(self, client, db_session, compte, monkeypatch):
        jeton = await self._jeton(client, db_session, compte, monkeypatch)
        compte.password_reset_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()

        reponse = await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton, "new_password": MOT_DE_PASSE_VALIDE}
        )

        assert reponse.status_code == 400
        assert "expiré" in reponse.json()["detail"]
        assert (await _recharger(db_session, compte)).password_reset_token is None

    async def test_un_jeton_sans_date_d_expiration_est_refuse(self, client, db_session, compte, monkeypatch):
        """NEW-66 : en l'absence d'information, on refuse.

        La vérification était conditionnée à la présence de la date, si bien
        qu'un jeton dont elle manquait n'était **jamais** considéré expiré et
        valait indéfiniment. Rien ne permet pourtant de dire l'âge d'un tel
        jeton — et c'est justement pourquoi il faut le refuser.
        """
        jeton = await self._jeton(client, db_session, compte, monkeypatch)
        compte.password_reset_expires = None
        await db_session.commit()

        reponse = await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton, "new_password": MOT_DE_PASSE_VALIDE}
        )

        assert reponse.status_code == 400
        assert (await _recharger(db_session, compte)).password_reset_token is None, "le jeton est efface"

    @pytest.mark.parametrize("faible", ["Court1!", "sansmajuscule1!", "SansChiffre!!"])
    async def test_un_mot_de_passe_faible_est_refuse(self, client, db_session, compte, monkeypatch, faible):
        """Dix caractères, une majuscule, un chiffre — la règle, telle qu'elle est.

        Ni minuscule ni symbole ne sont exigés : `SANSMINUSCULE1` et
        `SansSymbole11` passent. Le filet épingle la règle en vigueur, pas celle
        qu'on pourrait souhaiter.
        """
        jeton = await self._jeton(client, db_session, compte, monkeypatch)

        reponse = await client.post("/api/v1/auth/reset-password", json={"token": jeton, "new_password": faible})

        assert reponse.status_code == 422
        assert (await _recharger(db_session, compte)).password_reset_token == jeton, "le jeton reste utilisable"

    @pytest.mark.parametrize("accepte", ["SANSMINUSCULE1", "SansSymbole11"])
    async def test_ce_que_la_regle_laisse_passer(self, client, db_session, compte, monkeypatch, accepte):
        jeton = await self._jeton(client, db_session, compte, monkeypatch)

        reponse = await client.post("/api/v1/auth/reset-password", json={"token": jeton, "new_password": accepte})

        assert reponse.status_code == 200


class TestChangementDeMotDePasse:
    @pytest.fixture
    def entetes(self, compte: User) -> dict:
        return {"Authorization": f"Bearer {create_access_token(subject=str(compte.id))}"}

    async def test_le_mot_de_passe_actuel_est_exige(self, client, entetes):
        reponse = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "MauvaisMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
            headers=entetes,
        )

        assert reponse.status_code == 400

    async def test_le_changement_prend_effet_a_la_connexion_suivante(self, client, entetes, compte):
        reponse = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "AncienMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
            headers=entetes,
        )

        assert reponse.status_code == 200
        ancien = await client.post("/api/v1/auth/login", json={"email": compte.email, "password": "AncienMotDePasse1!"})
        assert ancien.status_code == 401

    async def test_sans_authentification_le_changement_est_refuse(self, client):
        reponse = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "AncienMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
        )

        assert reponse.status_code in (401, 403)


class TestPorteeDesSessions:
    """NEW-65 : changer son mot de passe coupe les sessions ouvertes.

    La révocation se faisait jeton par jeton, à la déconnexion, via une liste de
    blocage indexée par `jti` : rien ne rattachait un jeton déjà émis au mot de
    passe qui l'avait produit. Un jeton d'accès dérobé restait valable quinze
    minutes, un **jeton de rafraîchissement sept jours** — alors que
    réinitialiser son mot de passe est le geste par lequel on reprend la main
    sur un compte compromis.

    Chaque jeton porte désormais la **génération** qui l'a vu naître, et
    l'utilisateur celle en cours ; un changement de mot de passe incrémente la
    sienne et périme tout ce qui précède.
    """

    async def test_un_jeton_emis_avant_le_changement_ne_passe_plus(self, client, compte):
        jeton = create_access_token(subject=str(compte.id))
        entetes = {"Authorization": f"Bearer {jeton}"}
        assert (await client.get("/api/v1/auth/me", headers=entetes)).status_code == 200

        await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "AncienMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
            headers=entetes,
        )

        apres = await client.get("/api/v1/auth/me", headers=entetes)
        assert apres.status_code == 401
        assert "mot de passe a été modifié" in apres.json()["detail"]

    async def test_la_reinitialisation_coupe_aussi_les_sessions(self, client, db_session, compte, monkeypatch):
        jeton = create_access_token(subject=str(compte.id))
        entetes = {"Authorization": f"Bearer {jeton}"}
        await _demander_reinitialisation(client, compte.email, monkeypatch)
        jeton_reinit = (await _recharger(db_session, compte)).password_reset_token

        await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton_reinit, "new_password": MOT_DE_PASSE_VALIDE}
        )

        assert (await client.get("/api/v1/auth/me", headers=entetes)).status_code == 401

    async def test_un_jeton_de_rafraichissement_anterieur_ne_rouvre_pas_de_session(
        self, client, db_session, compte, monkeypatch
    ):
        """Le cœur du défaut : c'est lui qui vivait sept jours.

        Sans ce contrôle sur `/refresh`, un jeton d'accès coupé se remplaçait
        aussitôt par un neuf et la faille restait entière.
        """
        from app.core.security import create_refresh_token

        rafraichissement = create_refresh_token(subject=str(compte.id))
        await _demander_reinitialisation(client, compte.email, monkeypatch)
        jeton_reinit = (await _recharger(db_session, compte)).password_reset_token
        await client.post(
            "/api/v1/auth/reset-password", json={"token": jeton_reinit, "new_password": MOT_DE_PASSE_VALIDE}
        )

        client.cookies.set("refresh_token", rafraichissement)
        reponse = await client.post("/api/v1/auth/refresh")
        client.cookies.clear()

        assert reponse.status_code == 401

    async def test_la_session_qui_change_le_mot_de_passe_reste_ouverte(self, client, compte):
        """On ne déconnecte pas quelqu'un pour avoir suivi le bon conseil.

        La réponse repose des cookies neufs : la session courante continue,
        toutes les autres tombent.
        """
        jeton = create_access_token(subject=str(compte.id))
        entetes = {"Authorization": f"Bearer {jeton}"}

        reponse = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "AncienMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
            headers=entetes,
        )

        assert reponse.status_code == 200
        assert "access_token" in reponse.cookies
        suite = await client.get("/api/v1/auth/me")
        client.cookies.clear()
        assert suite.status_code == 200

    async def test_un_compte_sans_changement_garde_ses_sessions(self, client, compte):
        """Le déploiement ne doit déconnecter personne.

        Tant que `tokens_valid_from` est nul — donc tant qu'aucun mot de passe
        n'a changé depuis ce correctif — aucun jeton n'est refusé, pas même
        ceux émis avant lui, qui ne portent pas de date d'émission.
        """
        jeton = create_access_token(subject=str(compte.id))

        reponse = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {jeton}"})

        assert reponse.status_code == 200

    async def test_un_jeton_sans_generation_vaut_la_generation_zero(self, client, db_session, compte):
        """Les jetons d'avant le correctif n'en portent pas.

        Ils valent génération zéro, comme un compte dont le mot de passe n'a
        jamais changé depuis : ils passent tant que rien n'a bougé, et tombent
        au premier changement, avec les autres.
        """
        from jose import jwt as jose_jwt

        from app.core.config import settings

        ancien_style = jose_jwt.encode(
            {
                "sub": str(compte.id),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
                "type": "access",
                "jti": "sans-generation",
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        entetes = {"Authorization": f"Bearer {ancien_style}"}
        assert (await client.get("/api/v1/auth/me", headers=entetes)).status_code == 200

        compte.token_version = 1
        await db_session.commit()

        assert (await client.get("/api/v1/auth/me", headers=entetes)).status_code == 401

    async def test_le_compteur_avance_a_chaque_changement(self, client, db_session, compte):
        # Deux changements successifs doivent périmer deux fois : sans
        # incrément, le second laisserait passer les jetons du premier.
        entetes = {"Authorization": f"Bearer {create_access_token(subject=str(compte.id))}"}

        await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "AncienMotDePasse1!", "new_password": MOT_DE_PASSE_VALIDE},
            headers=entetes,
        )
        premier = (await _recharger(db_session, compte)).token_version
        client.cookies.clear()

        await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": MOT_DE_PASSE_VALIDE, "new_password": "EncoreUnAutre1!"},
            headers={"Authorization": f"Bearer {create_access_token(subject=str(compte.id), token_version=premier)}"},
        )
        client.cookies.clear()

        assert (await _recharger(db_session, compte)).token_version == premier + 1


class TestUneSeuleRegleDeMotDePasse:
    """NEW-67 : la création par l'administration passait par une règle plus faible.

    Quatre chemins posent un mot de passe — inscription, changement,
    réinitialisation, et création ou modification depuis l'administration. Les
    trois premiers exigeaient dix caractères, une majuscule et un chiffre ; le
    quatrième se contentait de **huit caractères, sans aucune contrainte de
    composition**. Un compte créé depuis l'administration pouvait donc avoir
    « aaaaaaaa » pour mot de passe, ce qui en faisait la porte la plus basse de
    la maison.

    Le validateur de la réinitialisation, lui, redisait la règle mot pour mot au
    lieu de l'appeler : identique ce jour-là, libre de diverger le lendemain.
    Les quatre appellent désormais `_validate_password_complexity`.
    """

    @pytest.mark.parametrize(
        "modele",
        ["RegisterRequest", "PasswordChangeRequest", "ResetPasswordRequest", "UserCreate", "UserUpdate"],
    )
    @pytest.mark.parametrize("faible", ["Court1!", "sansmajuscule1", "SansChiffre"])
    def test_aucun_chemin_n_accepte_un_mot_de_passe_faible(self, modele, faible):
        import pydantic

        from app.api.v1.endpoints.auth import ResetPasswordRequest
        from app.schemas.auth import PasswordChangeRequest, RegisterRequest
        from app.schemas.user import UserCreate, UserUpdate

        classes = {
            "RegisterRequest": (RegisterRequest, {"email": "a@b.com", "password": faible}),
            "PasswordChangeRequest": (PasswordChangeRequest, {"current_password": "x", "new_password": faible}),
            "ResetPasswordRequest": (ResetPasswordRequest, {"token": "t", "new_password": faible}),
            "UserCreate": (UserCreate, {"email": "a@b.com", "password": faible}),
            "UserUpdate": (UserUpdate, {"password": faible}),
        }
        classe, champs = classes[modele]

        with pytest.raises(pydantic.ValidationError):
            classe(**champs)

    def test_une_modification_sans_mot_de_passe_reste_possible(self):
        from app.schemas.user import UserUpdate

        # `UserUpdate.password` est facultatif : changer le seul prénom ne doit
        # pas buter sur la règle de complexité.
        assert UserUpdate(first_name="Loann").password is None
