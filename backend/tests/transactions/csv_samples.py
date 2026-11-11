CRYPTO_COM = (
    "Timestamp (UTC),Transaction Description,Currency,Amount,To Currency,To Amount,Native Currency,Native Amount,"
    "Native Amount (in USD),Transaction Kind,Transaction Hash\n"
    "2025-01-02 10:00:00,CRO -> BTC,BTC,0.001,CRO,-500,EUR,90,95,crypto_exchange,\n"
    "2025-01-02 11:00:00,ETH -> SOL,ETH,-0.5,SOL,8,EUR,1500,1600,crypto_exchange,\n"
    "2025-01-02 12:00:00,Received ADA,ADA,100,,,EUR,80,85,crypto_exchange,\n"
    "2025-01-02 13:00:00,Sent ADA,ADA,-100,,,EUR,80,85,crypto_exchange,\n"
    "2025-01-03 09:00:00,Buy BTC,EUR,-200,BTC,0.002,EUR,200,210,viban_purchase,\n"
    "2025-01-03 10:00:00,Card buy ETH,ETH,0.1,,,EUR,300,310,trading.crypto_purchase.card,\n"
    "2025-01-03 11:00:00,Google Pay EUR,EUR,50,,,EUR,50,52,trading.crypto_purchase.google_pay,\n"
    "2025-01-04 09:00:00,Sell DOT,DOT,-10,EUR,60,EUR,60,62,crypto_viban_exchange,\n"
    "2025-01-04 10:00:00,Deposit XRP,XRP,50,,,EUR,25,26,crypto_deposit,0xabc\n"
    "2025-01-04 11:00:00,Withdraw XRP,XRP,-20,,,EUR,10,11,crypto_withdrawal,0xdef\n"
    "2025-01-05 09:00:00,Earn interest,USDC,0.5,,,EUR,0.46,0.5,crypto_earn_interest_paid,\n"
    "2025-01-05 10:00:00,Referral,CRO,25,,,EUR,2,2.1,referral_bonus,\n"
    "2025-01-05 11:00:00,Balance Conversion,DOGE,-30,,,EUR,3,3.1,crypto_wallet_swap_debited,\n"
    "2025-01-05 12:00:00,Balance Conversion,SHIB,1000,,,EUR,3,3.1,crypto_wallet_swap_credited,\n"
    "2025-01-06 09:00:00,Lockup,CRO,-100,,,EUR,8,8.5,lockup_lock,\n"
    "2025-01-06 10:00:00,Zero deposit,LTC,0,,,EUR,0,0,crypto_deposit,\n"
    "2025-01-06 11:00:00,Bad amount,LTC,abc,,,EUR,1,1,crypto_deposit,\n"
    "not a date,Bad time,LTC,1,,,EUR,1,1,crypto_deposit,\n"
    "2025-01-07T08:30:00.250,Supercharger,ATOM,0.2,,,EUR,1.5,1.6,supercharger_reward_to_app_credited,\n"
    "07/01/2025 09:00,Staking,ATOM,0.1,,,EUR,0.7,0.8,staking_reward,\n"
)

BINANCE = (
    "User_ID,UTC_Time,Account,Operation,Coin,Change,Remark\n"
    "1,2025-02-01 10:00:00,Spot,Buy,BTC,0.01,\n"
    "1,2025-02-01 10:00:00,Spot,Buy,EUR,-900,\n"
    "1,2025-02-01 10:00:00,Spot,Commission,BTC,-0.00001,\n"
    "1,2025-02-02 10:00:00,Spot,Sell,ETH,-0.2,\n"
    "1,2025-02-03 10:00:00,Spot,Deposit,SOL,5,\n"
    "1,2025-02-03 11:00:00,Spot,Withdraw,SOL,-2,\n"
    "1,2025-02-04 10:00:00,Earn,Simple Earn Flexible Interest,USDC,0.03,\n"
    "1,2025-02-04 11:00:00,Earn,Simple Earn Flexible Subscription,USDC,-100,\n"
    "1,2025-02-04 12:00:00,Earn,Simple Earn Locked Redemption,USDC,100,\n"
    "1,2025-02-05 10:00:00,Spot,Distribution,BNB,0.01,\n"
    "1,2025-02-05 11:00:00,Spot,Convert,ADA,-50,\n"
    "1,2025-02-05 11:00:00,Spot,Convert,DOT,4,\n"
    "1,2025-02-05 12:00:00,Spot,Small Assets Exchange BNB,BNB,0.002,\n"
    "1,2025-02-06 10:00:00,Spot,Transfer Between Main and Funding Wallet,BTC,0.01,\n"
    "1,2025-02-06 11:00:00,Spot,Deposit,SOL,0,\n"
    "1,2025-02-06 12:00:00,Spot,Deposit,SOL,x,\n"
    "1,2025-02-07T10:00:00Z,Spot,ETH 2.0 Staking Rewards,ETH,0.0004,\n"
)

KRAKEN = (
    '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'
    '"L1","R1","2025-03-01 10:00:00","deposit","","currency","XXBT","0.05","0","0.05"\n'
    '"L2","R2","2025-03-01 11:00:00","trade","","currency","XXBT","0.01","0.00002","0.06"\n'
    '"L3","R2","2025-03-01 11:00:00","trade","","currency","ZEUR","-900","1.5","100"\n'
    '"L4","R3","2025-03-02 10:00:00","trade","","currency","XETH","-0.3","0.0001","0.7"\n'
    '"L5","R4","2025-03-02 11:00:00","staking","","currency","DOT.S","0.4","0","10.4"\n'
    '"L6","R5","2025-03-02 12:00:00","reward","","currency","XXDG","15","0","15"\n'
    '"L7","R6","2025-03-03 10:00:00","earn","","currency","USDC","0.2","0","50.2"\n'
    '"L8","R7","2025-03-03 11:00:00","spend","","currency","ADA","-40","0","0"\n'
    '"L9","R8","2025-03-03 12:00:00","receive","","currency","ADA","40","0","40"\n'
    '"L10","R9","2025-03-04 10:00:00","withdrawal","","currency","XXBT","-0.02","0.0001","0.04"\n'
    '"L11","R10","2025-03-04 11:00:00","transfer","","currency","SOL","1","0","1"\n'
    '"L12","R11","2025-03-04 12:00:00","margin","","currency","XXBT","0.01","0","0.05"\n'
    '"L13","R12","2025-03-05 10:00:00.4321","bonus","","currency","XXRP","3","0","3"\n'
    '"L14","R13","2025-03-05 11:00:00","credit","","currency","ZGBP","10","0","10"\n'
    '"L15","R14","2025-03-05 12:00:00","deposit","","currency","XLTC","0","0","0"\n'
    '"L16","R15","05/03/2025","deposit","","currency","XLTC","1","0","1"\n'
    '"L17","R16","2025-03-06 10:00:00","deposit","","currency","XLTC","1,5","0","1"\n'
)

GENERIC = (
    "symbol,type,quantity,price,fee,date,notes\n"
    "btc,achat,0.1,40000,5,2025-01-10 10:00:00,premier achat\n"
    "BTC,sell,-0.02,42000,1,2025-01-11,\n"
    "eth,vente,0.5,2500,0,10/01/2025 09:00:00,\n"
    "AAPL,dividende,1,0.24,0,01/10/2025,dividende\n"
    "SOL,deposit,3,0,,2025-01-12T08:00:00Z,\n"
    "SOL,withdrawal,1,0,0.01,12-01-2025,\n"
    "DOT,staking,10,6,0,12-01-2025 10:00:00,\n"
    "ADA,swap,5,0.3,0,2025-01-13,\n"
    ",buy,1,1,0,2025-01-13,sans symbole\n"
    "XRP,buy,2,0.5,0,,sans date\n"
    "XRP,buy,3,0.5,0,Jan 13 2025,date inconnue\n"
    "LTC,buy,abc,70,0,2025-01-14,\n"
    "EUR,deposit,100,1,0,2025-01-14,\n"
)

GENERIC_SEMICOLON = "symbol;type;quantity;price;fee;date\nBTC;buy;0,1;40000;0;2025-01-10\nETH;buy;1;2500;0;2025-01-10\n"
GENERIC_TAB = "symbol\ttype\tquantity\tprice\nBTC\tbuy\t0.1\t40000\n"
UNKNOWN = "foo,bar,baz\n1,2,3\n"
