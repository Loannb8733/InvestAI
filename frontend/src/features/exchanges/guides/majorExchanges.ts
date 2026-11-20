import type { ExchangeGuideData } from './types'

export const MAJOR_EXCHANGE_GUIDES: ExchangeGuideData[] = [
  {
    id: 'binance',
    name: 'Binance',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de retrait ou de trading. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Connectez-vous à votre compte Binance',
        link: {
          label: 'binance.com > Gestion API',
          href: 'https://www.binance.com/fr/my/settings/api-management',
        },
        details: ['Ou : icône profil en haut à droite > **Gestion API**'],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: [
          'Cliquez sur **"Créer une API"**, choisissez **"Clé API générée par le système"**, '
          + 'puis donnez-lui un nom (ex: "InvestAI").',
          'Binance vous demandera une vérification 2FA (email + authenticator).',
        ],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Lecture seule** (Enable Reading)'],
        permissionsForbidden: [
          'Enable Spot & Margin Trading',
          'Enable Withdrawals',
          'Enable Futures',
        ],
      },
      {
        title: 'Copiez vos clés',
        details: ['Binance affiche deux valeurs :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'Secret Key', field: 'Clé secrète' },
        ],
        warning: 'La Secret Key n\'est affichée qu\'une seule fois ! Copiez-la immédiatement.',
      },
      {
        title: 'Collez-les dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Binance, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'kraken',
    name: 'Kraken',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Connectez-vous à votre compte Kraken',
        link: {
          label: 'kraken.com > Sécurité > API',
          href: 'https://www.kraken.com/u/security/api',
        },
        details: ['Ou : **Paramètres** (icône engrenage) > **Sécurité** > **API**'],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: [
          'Cliquez sur **"Add key"** (ou "Ajouter une clé"). '
          + 'Donnez-lui un nom descriptif (ex: "InvestAI").',
        ],
      },
      {
        title: 'Configurez les permissions',
        details: ['Dans la section **"Permissions"**, cochez uniquement :'],
        permissionsChecked: [
          '**Query Funds** — consulter vos soldes',
          '**Query Open Orders & Trades** — lire l\'historique de trades',
          '**Query Closed Orders & Trades** — lire les ordres passés',
          '**Query Ledger Entries** — lire les mouvements de fonds',
        ],
        permissionsForbidden: [
          'Create & Modify Orders',
          'Cancel/Close Orders',
          'Withdraw Funds',
        ],
      },
      {
        title: 'Générez et copiez vos clés',
        details: ['Cliquez sur **"Generate key"**. Kraken affiche :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'Private Key', field: 'Clé secrète' },
        ],
        warning: 'La Private Key n\'est affichée qu\'une seule fois ! Copiez-la immédiatement.',
      },
      {
        title: 'Collez-les dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Kraken, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'coinbase',
    name: 'Coinbase',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de création, d\'achat, de vente ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Paramètres > API',
        link: {
          label: 'coinbase.com/settings/api',
          href: 'https://www.coinbase.com/settings/api',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: ['Cliquez sur **"New API Key"**.'],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: [
          '**wallet:accounts:read**',
          '**wallet:trades:read**',
          '**wallet:transactions:read**',
          '**wallet:deposits:read**',
          '**wallet:withdrawals:read**',
        ],
        permissionsForbidden: [
          'wallet:accounts:create',
          'wallet:buys:create',
          'wallet:sells:create',
          'wallet:withdrawals:create',
        ],
      },
      {
        title: 'Copiez vos clés',
        details: ['Coinbase affiche deux valeurs :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'API Secret', field: 'Clé secrète' },
        ],
        warning: 'L\'API Secret n\'est affiché qu\'une seule fois ! Copiez-le immédiatement.',
      },
      {
        title: 'Collez-les dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Coinbase, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'cryptocom',
    name: 'Crypto.com',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez sur Crypto.com Exchange > API Management',
        link: {
          label: 'crypto.com/exchange > API Management',
          href: 'https://crypto.com/exchange/personal/api-management',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: ['Cliquez sur **"Create new API Key"** et donnez-lui un nom (ex: "InvestAI").'],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Read Only**'],
        permissionsForbidden: ['Can Trade', 'Can Withdraw'],
      },
      {
        title: 'Copiez vos clés',
        details: ['Crypto.com affiche deux valeurs :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'Secret Key', field: 'Clé secrète' },
        ],
        warning: 'La Secret Key n\'est affichée qu\'une seule fois ! Copiez-la immédiatement.',
      },
      {
        title: 'Collez-les dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Crypto.com, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'kucoin',
    name: 'KuCoin',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de transfert. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Account > API Management',
        link: {
          label: 'kucoin.com/account/api',
          href: 'https://www.kucoin.com/account/api',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: [
          'Cliquez sur **"Create API"**, choisissez un nom et définissez un **passphrase** (à retenir !).',
        ],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**General** — consulter vos soldes et historique'],
        permissionsForbidden: ['Trade', 'Transfer'],
      },
      {
        title: 'Copiez vos clés et notez le passphrase',
        details: ['KuCoin affiche trois valeurs :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'Secret Key', field: 'Clé secrète' },
          { name: 'Passphrase', field: 'Passphrase' },
        ],
        warning:
          'La Secret Key n\'est affichée qu\'une seule fois ! Copiez-la immédiatement. '
          + 'KuCoin nécessite 3 champs (incluez le passphrase !).',
      },
      {
        title: 'Collez les 3 valeurs dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez KuCoin, et collez vos trois valeurs (API Key, Secret, Passphrase).',
        ],
      },
    ],
  },
]
