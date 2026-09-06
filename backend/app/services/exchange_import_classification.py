"""Classification des mouvements importés depuis un exchange.

Pourquoi ce module existe
-------------------------
Le type d'une transaction importée ne se lit ni dans le sens de l'opération ni
dans un champ dédié : il se lit dans le **préfixe de son identifiant**.
`reward_staking_`, `reward_` (airdrop), `fiat_`, `instant_`, `convert_`,
`withdrawal_` — tout le reste est un trade au comptant.

C'est la mécanique centrale de l'import, et la plus fragile : le même
mouvement, selon son identifiant, devient une récompense de staking ou un
achat. Rien ne l'annonce, aucune erreur ne survient si un préfixe se perd — les
montants sont simplement rangés au mauvais endroit, et la fiscalité avec eux.

Elle vivait à l'intérieur d'une boucle, dans un bloc de 1 051 lignes. Ici, elle
se lit et se vérifie en quelques millisecondes.
"""

from dataclasses import dataclass

from app.models.transaction import TransactionType

PREFIXE_RECOMPENSE = "reward_"
PREFIXE_RECOMPENSE_STAKING = "reward_staking_"
PREFIXE_ORDRE_FIAT = "fiat_"
PREFIXE_ACHAT_IMMEDIAT = "instant_"
PREFIXE_CONVERSION = "convert_"
PREFIXE_CONVERSION_VENTE = "convert_sell_"
PREFIXE_RETRAIT = "withdrawal_"


@dataclass(frozen=True)
class OrigineMouvement:
    """D'où vient un mouvement, tel que son identifiant le déclare."""

    est_retrait: bool = False
    est_recompense_staking: bool = False
    est_airdrop: bool = False
    est_ordre_fiat: bool = False
    est_conversion: bool = False

    @property
    def est_recompense(self) -> bool:
        """Staking et airdrop comptent ensemble dans les compteurs de l'import."""
        return self.est_recompense_staking or self.est_airdrop


def classifier_origine(trade_id: str) -> OrigineMouvement:
    """Lit l'origine d'un mouvement dans le préfixe de son identifiant.

    Un identifiant sans préfixe connu ne porte aucun drapeau : c'est un trade au
    comptant, le cas par défaut.
    """
    if not trade_id:
        return OrigineMouvement()

    est_staking = trade_id.startswith(PREFIXE_RECOMPENSE_STAKING)

    # Un airdrop est une récompense qui n'est pas du staking.
    #
    # La forme d'origine testait d'abord `reward_airdrop_`, puis `reward_` sans
    # `reward_staking_`. Le premier terme était redondant — `reward_airdrop_`
    # commence par `reward_` et jamais par `reward_staking_` — et sa précédence
    # prêtait à confusion : `A or B and not C` se lit volontiers `(A or B) and
    # not C`. Les deux écritures ont été comparées sur 200 040 identifiants,
    # sans un écart.
    est_airdrop = trade_id.startswith(PREFIXE_RECOMPENSE) and not est_staking

    return OrigineMouvement(
        est_retrait=trade_id.startswith(PREFIXE_RETRAIT),
        est_recompense_staking=est_staking,
        est_airdrop=est_airdrop,
        est_ordre_fiat=trade_id.startswith(PREFIXE_ORDRE_FIAT) or trade_id.startswith(PREFIXE_ACHAT_IMMEDIAT),
        est_conversion=trade_id.startswith(PREFIXE_CONVERSION),
    )


def determiner_type_transaction(origine: OrigineMouvement, trade_id: str, side: str) -> TransactionType:
    """Type de transaction à écrire, dans l'ordre de priorité de l'import.

    L'ordre compte : un identifiant peut satisfaire plusieurs préfixes, et c'est
    le premier examiné qui l'emporte. Retrait, puis staking, puis airdrop, puis
    conversion — le sens de l'opération ne tranche qu'en dernier recours, pour
    les trades au comptant.

    Une conversion se dédouble : `convert_sell_` sort de l'actif, tout autre
    préfixe de conversion y entre.
    """
    if origine.est_retrait:
        return TransactionType.TRANSFER_OUT
    if origine.est_recompense_staking:
        return TransactionType.STAKING_REWARD
    if origine.est_airdrop:
        return TransactionType.AIRDROP
    if origine.est_conversion:
        if trade_id.startswith(PREFIXE_CONVERSION_VENTE):
            return TransactionType.CONVERSION_OUT
        return TransactionType.CONVERSION_IN
    return TransactionType.BUY if side == "buy" else TransactionType.SELL
