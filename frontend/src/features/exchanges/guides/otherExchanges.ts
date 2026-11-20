import type { ExchangeGuideData } from './types'

export const OTHER_EXCHANGE_GUIDES: ExchangeGuideData[] = [
  {
    id: 'bybit',
    name: 'Bybit',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading, retrait ou transfert. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Account & Security > API Management',
        link: {
          label: 'bybit.com > API Management',
          href: 'https://www.bybit.com/app/user/api-management',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: [
          'Cliquez sur **"Create New Key"**, puis choisissez **"System-generated API Keys"**.',
        ],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Read-Only**'],
        permissionsForbidden: ['Trade', 'Withdraw', 'Transfer'],
      },
      {
        title: 'Copiez vos clés',
        details: ['Bybit affiche deux valeurs :'],
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
          + 'sélectionnez Bybit, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'okx',
    name: 'OKX',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Profile > API Management',
        link: {
          label: 'okx.com/account/my-api',
          href: 'https://www.okx.com/account/my-api',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: [
          'Cliquez sur **"Create API Key"**, choisissez un nom et définissez un **passphrase**.',
        ],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Read Only**'],
        permissionsForbidden: ['Trade', 'Withdraw'],
      },
      {
        title: 'Copiez vos clés et notez le passphrase',
        details: ['OKX affiche trois valeurs :'],
        keys: [
          { name: 'API Key', field: 'Clé API' },
          { name: 'Secret Key', field: 'Clé secrète' },
          { name: 'Passphrase', field: 'Passphrase' },
        ],
        warning:
          'La Secret Key n\'est affichée qu\'une seule fois ! Copiez-la immédiatement. '
          + 'OKX nécessite 3 champs (incluez le passphrase !).',
      },
      {
        title: 'Collez les 3 valeurs dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez OKX, et collez vos trois valeurs (API Key, Secret, Passphrase).',
        ],
      },
    ],
  },
  {
    id: 'bitpanda',
    name: 'Bitpanda',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Bitpanda Pro > Settings > API Keys',
        link: {
          label: 'exchange.bitpanda.com/account/api',
          href: 'https://exchange.bitpanda.com/account/api',
        },
        details: [],
      },
      {
        title: 'Générez une nouvelle clé',
        details: ['Cliquez sur **"Generate New Key"**.'],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Read**'],
        permissionsForbidden: ['Trade', 'Withdraw'],
      },
      {
        title: 'Copiez votre clé API',
        details: ['Bitpanda ne nécessite qu\'une seule clé API (pas de clé secrète) :'],
        keys: [{ name: 'API Key', field: 'Clé API' }],
        warning:
          'Bitpanda ne nécessite QU\'UNE clé API, pas de secret. Seul le champ "Clé API" est requis.',
      },
      {
        title: 'Collez-la dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Bitpanda, et collez votre clé API (seul champ requis).',
        ],
      },
    ],
  },
  {
    id: 'bitstamp',
    name: 'Bitstamp',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions d\'achat, de vente ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Settings > Security > API Access',
        link: {
          label: 'bitstamp.net/settings/api',
          href: 'https://www.bitstamp.net/settings/api/',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: ['Cliquez sur **"Create New API Key"**.'],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Account balance**', '**User transactions**'],
        permissionsForbidden: ['Buy/Sell', 'Withdrawals'],
      },
      {
        title: 'Activez et copiez vos clés',
        details: ['Activez la clé via la confirmation par email, puis copiez :'],
        keys: [
          { name: 'Key', field: 'Clé API' },
          { name: 'Secret', field: 'Clé secrète' },
        ],
        warning: 'La Secret n\'est affichée qu\'une seule fois ! Copiez-la immédiatement.',
      },
      {
        title: 'Collez-les dans InvestAI',
        details: [
          'Cliquez sur **"Connecter un exchange"** en haut de cette page, '
          + 'sélectionnez Bitstamp, et collez vos deux clés.',
        ],
      },
    ],
  },
  {
    id: 'gateio',
    name: 'Gate.io',
    readOnlyWarning:
      'Ne cochez **jamais** les permissions de trading ou de retrait. '
      + 'InvestAI a uniquement besoin de **lire** vos soldes et votre historique.',
    steps: [
      {
        title: 'Allez dans Account > API Management',
        link: {
          label: 'gate.io > API Management',
          href: 'https://www.gate.io/myaccount/api_key_manage',
        },
        details: [],
      },
      {
        title: 'Créez une nouvelle clé API',
        details: ['Cliquez sur **"Create API Key"**.'],
      },
      {
        title: 'Configurez les permissions',
        details: ['Cochez uniquement :'],
        permissionsChecked: ['**Spot Read-Only**', '**Wallet Read-Only**'],
        permissionsForbidden: ['Spot Trade', 'Wallet Withdraw'],
      },
      {
        title: 'Copiez vos clés',
        details: ['Gate.io affiche deux valeurs :'],
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
          + 'sélectionnez Gate.io, et collez vos deux clés.',
        ],
      },
    ],
  },
]
