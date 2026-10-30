from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.core.security import encrypt_api_key
from app.domains.exchanges.clients import crypto_portfolio, open_client
from app.domains.exchanges.connectors.registry import SUPPORTED_EXCHANGES
from app.domains.exchanges.failures import describe, rollback_and_mark
from app.domains.exchanges.models import APIKey, ColdWalletAddress
from app.domains.exchanges.schemas import (
    APIKeyCreate,
    APIKeyUpdate,
    BalanceSyncResult,
    ColdWalletCreate,
    ConnectionTestResult,
)
from app.domains.exchanges.sync.symbols import holdings
from app.domains.portfolio.models import Asset, AssetType

KEY_NOT_FOUND = "Clé API non trouvée"
SHOWN_BALANCES = 10
QUANTITY_EPSILON = Decimal("0.00000001")


class SyncFailedError(DomainError):
    status_code = 500


class ExchangeAccounts:
    """Clés d'API, test de connexion, synchronisation des soldes et noms des wallets froids d'un utilisateur."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def keys(self, user_id: UUID) -> Sequence[APIKey]:
        return (await self._session.execute(select(APIKey).where(APIKey.user_id == user_id))).scalars().all()

    async def key(self, user_id: UUID, key_id: UUID) -> APIKey:
        query = select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        key = (await self._session.execute(query)).scalar_one_or_none()
        if key is None:
            raise NotFoundError(KEY_NOT_FOUND)
        return key

    async def add_key(self, user_id: UUID, data: APIKeyCreate) -> APIKey:
        exchange = data.exchange.lower()
        supported = [str(e["id"]) for e in SUPPORTED_EXCHANGES]
        if exchange not in supported:
            raise DomainError(f"Exchange non supporté. Exchanges supportés: {', '.join(supported)}")
        key = APIKey(
            user_id=user_id,
            exchange=exchange,
            label=data.label,
            encrypted_api_key=encrypt_api_key(data.api_key),
            encrypted_secret_key=encrypt_api_key(data.secret_key) if data.secret_key else None,
            encrypted_passphrase=encrypt_api_key(data.passphrase) if data.passphrase else None,
            is_active=True,
        )
        self._session.add(key)
        await self._session.flush()
        await self._session.refresh(key)
        return key

    async def update_key(self, user_id: UUID, key_id: UUID, data: APIKeyUpdate) -> APIKey:
        """Seuls les secrets fournis sont remplacés."""
        key = await self.key(user_id, key_id)
        if data.label is not None:
            key.label = data.label
        if data.is_active is not None:
            key.is_active = data.is_active
        if data.api_key:
            key.encrypted_api_key = encrypt_api_key(data.api_key)
        if data.secret_key:
            key.encrypted_secret_key = encrypt_api_key(data.secret_key)
        if data.passphrase:
            key.encrypted_passphrase = encrypt_api_key(data.passphrase)
        await self._session.flush()
        await self._session.refresh(key)
        return key

    async def remove_key(self, user_id: UUID, key_id: UUID) -> None:
        await self._session.delete(await self.key(user_id, key_id))
        await self._session.flush()

    async def test_key(self, user_id: UUID, key_id: UUID) -> ConnectionTestResult:
        """Teste la connexion ; le succès montre dix soldes, l'échec est inscrit sur la clé."""
        key = await self.key(user_id, key_id)
        try:
            client = open_client(key)
            if await client.test_connection():
                balances = await client.get_balances()
                key.last_sync_at = datetime.now(UTC)
                key.last_error = None
                shown = {b.symbol: float(b.total) for b in balances[:SHOWN_BALANCES]}
                return ConnectionTestResult(success=True, message="Connexion réussie", balance=shown or None)
            detail = await client.connection_error() or "Échec de la connexion"
        except Exception as exc:  # noqa: BLE001
            key.last_error = describe(exc)
            return ConnectionTestResult(
                success=False, message="Erreur de connexion. Vérifiez vos identifiants et réessayez."
            )
        key.last_error = detail
        return ConnectionTestResult(success=False, message=f"Échec de la connexion: {detail}")

    async def sync_balances(self, user_id: UUID, key_id: UUID) -> BalanceSyncResult:
        """Recopie les soldes de l'exchange dans les actifs de sa plateforme, sans créer de transaction."""
        key = await self.key(user_id, key_id)
        try:
            client = open_client(key)
            balances = await client.get_balances()
            if not balances:
                return BalanceSyncResult(message="Aucun solde trouvé sur l'exchange", synced_assets=0)
            totals = holdings(balances).totals
            portfolio = await crypto_portfolio(self._session, user_id, client.exchange_name)
            assets = (
                (await self._session.execute(select(Asset).where(Asset.portfolio_id == portfolio.id))).scalars().all()
            )
            on_platform = {(a.symbol, a.exchange): a for a in assets}
            synced = 0
            for symbol, total in totals.items():
                asset = on_platform.get((symbol, client.exchange_name)) or on_platform.get((symbol, ""))
                created = asset is None
                if asset is None:
                    asset = Asset(
                        portfolio_id=portfolio.id,
                        symbol=symbol,
                        name=symbol,
                        asset_type=AssetType.CRYPTO,
                        quantity=Decimal("0"),
                        avg_buy_price=Decimal("0"),
                        currency="EUR",
                        exchange=client.exchange_name,
                    )
                    self._session.add(asset)
                asset.exchange = client.exchange_name
                if created or abs(total - asset.quantity) > QUANTITY_EPSILON:
                    asset.quantity = total
                    synced += 1
            key.last_sync_at = datetime.now(UTC)
            key.mark_success()
            await self._session.flush()
        except Exception as exc:
            await rollback_and_mark(self._session, key_id, exc)
            raise SyncFailedError(
                "La synchronisation a échoué. Réessayez ; si le problème persiste, contactez le support."
            ) from exc
        return BalanceSyncResult(
            message="Synchronisation réussie",
            synced_assets=synced,
            portfolio_id=str(portfolio.id),
            portfolio_name=portfolio.name,
        )

    async def wallets(self, user_id: UUID) -> Sequence[ColdWalletAddress]:
        query = (
            select(ColdWalletAddress).where(ColdWalletAddress.user_id == user_id).order_by(ColdWalletAddress.created_at)
        )
        return (await self._session.execute(query)).scalars().all()

    async def name_wallet(self, user_id: UUID, data: ColdWalletCreate) -> ColdWalletAddress:
        query = select(ColdWalletAddress).where(
            ColdWalletAddress.user_id == user_id, ColdWalletAddress.address == data.address
        )
        wallet = (await self._session.execute(query)).scalar_one_or_none()
        if wallet is None:
            wallet = ColdWalletAddress(user_id=user_id, address=data.address, label=data.label)
            self._session.add(wallet)
        else:
            wallet.label = data.label
        await self._session.flush()
        await self._session.refresh(wallet)
        return wallet

    async def remove_wallet(self, user_id: UUID, wallet_id: UUID) -> None:
        query = select(ColdWalletAddress).where(ColdWalletAddress.id == wallet_id, ColdWalletAddress.user_id == user_id)
        wallet = (await self._session.execute(query)).scalar_one_or_none()
        if wallet is None:
            raise NotFoundError("Cold wallet mapping not found")
        await self._session.delete(wallet)
        await self._session.flush()
