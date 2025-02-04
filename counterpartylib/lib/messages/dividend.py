#! /usr/bin/python3

"""Pay out dividends."""
import json
import struct
import decimal
D = decimal.Decimal
import logging
logger = logging.getLogger(__name__)

from counterpartylib.lib import (config, exceptions, util, message_type)

FORMAT_1 = '>QQ'
LENGTH_1 = 8 + 8
FORMAT_2 = '>QQQ'
LENGTH_2 = 8 + 8 + 8
ID = 50

def initialise (db):
    cursor = db.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS dividends(
                      tx_index INTEGER PRIMARY KEY,
                      tx_hash TEXT UNIQUE,
                      block_index INTEGER,
                      source TEXT,
                      asset TEXT,
                      dividend_asset TEXT,
                      quantity_per_unit INTEGER,
                      fee_paid INTEGER,
                      status TEXT,
                      FOREIGN KEY (tx_index, tx_hash, block_index) REFERENCES transactions(tx_index, tx_hash, block_index))
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      block_index_idx ON dividends (block_index)
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      source_idx ON dividends (source)
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      asset_idx ON dividends (asset)
                   ''')

def validate (db, source, quantity_per_unit, asset, dividend_asset, block_index):
    cursor = db.cursor()
    problems = []

    if asset == config.BTC:
        problems.append('cannot pay dividends to holders of {}'.format(config.BTC))
    if asset == config.XCP:
        if (not block_index >= 317500) or block_index >= 320000 or config.TESTNET or config.REGTEST:   # Protocol change.
            problems.append('cannot pay dividends to holders of {}'.format(config.XCP))

    if quantity_per_unit <= 0:
        problems.append('non‐positive quantity per unit')

    # For SQLite3
    if quantity_per_unit > config.MAX_INT:
        problems.append('integer overflow')

    # Examine asset.
    try:
        divisible = util.is_divisible(db, asset)
    except AssetError:
        problems.append('no such asset, {}.'.format(asset))
        return None, None, problems, 0
    
    # Only issuer can pay dividends.
    if block_index >= 320000 or config.TESTNET or config.REGTEST:   # Protocol change.
        issuer = util.get_asset_issuer(db, asset)
    
        if issuer != source:
            problems.append('only issuer can pay dividends')

    # Examine dividend asset.
    try:
        dividend_divisible = util.is_divisible(db, dividend_asset)
    except AssetError:
        problems.append('no such dividend asset, {}.'.format(dividend_asset))
        return None, None, problems, 0
        
    # Calculate dividend quantities.
    exclude_empty = False
    if util.enabled('zero_quantity_value_adjustment_1'):
        exclude_empty = True
    holders = util.holders(db, asset, exclude_empty)

    outputs = []
    addresses = []
    dividend_total = 0
    for holder in holders:
        if block_index < 294500 and not (config.TESTNET or config.REGTEST): # Protocol change.
            if holder['escrow']: continue

        address = holder['address']
        address_quantity = holder['address_quantity']

        if block_index >= 296000 or config.TESTNET or config.REGTEST: # Protocol change.
            if address == source: continue

        dividend_quantity = address_quantity * quantity_per_unit

        if divisible: dividend_quantity /= config.UNIT
        if not util.enabled('nondivisible_dividend_fix') and not dividend_divisible: dividend_quantity /= config.UNIT # Pre-fix behaviour

        if dividend_asset == config.BTC and dividend_quantity < config.DEFAULT_MULTISIG_DUST_SIZE: continue    # A bit hackish.
        dividend_quantity = int(dividend_quantity)

        outputs.append({'address': address, 'address_quantity': address_quantity, 'dividend_quantity': dividend_quantity})
        addresses.append(address)
        dividend_total += dividend_quantity

    if not dividend_total: problems.append('zero dividend')

    if dividend_asset != config.BTC:
        dividend_balances = list(cursor.execute('''SELECT * FROM balances WHERE (address = ? AND asset = ?)''', (source, dividend_asset)))
        if not dividend_balances or dividend_balances[0]['quantity'] < dividend_total:
            problems.append('insufficient funds ({})'.format(dividend_asset))

    fee = 0
    if not problems and dividend_asset != config.BTC:
        holder_count = len(set(addresses))
        if block_index >= 330000 or config.TESTNET or config.REGTEST: # Protocol change.
            fee = int(0.0002 * config.UNIT * holder_count)
        if fee:
            balances = list(cursor.execute('''SELECT * FROM balances WHERE (address = ? AND asset = ?)''', (source, config.XCP)))
            if not balances or balances[0]['quantity'] < fee:
                problems.append('insufficient funds ({})'.format(config.XCP))

    if not problems and dividend_asset == config.XCP:
        total_cost = dividend_total + fee
        if not dividend_balances or dividend_balances[0]['quantity'] < total_cost:
            problems.append('insufficient funds ({})'.format(dividend_asset))

    # For SQLite3
    if fee > config.MAX_INT or dividend_total > config.MAX_INT:
        problems.append('integer overflow')

    cursor.close()

    return dividend_total, outputs, problems, fee

def compose (db, source, quantity_per_unit, asset, dividend_asset):
    # resolve subassets
    asset = util.resolve_subasset_longname(db, asset)
    dividend_asset = util.resolve_subasset_longname(db, dividend_asset)

    dividend_total, outputs, problems, fee = validate(db, source, quantity_per_unit, asset, dividend_asset, util.CURRENT_BLOCK_INDEX)
    if problems: raise exceptions.ComposeError(problems)
    logger.info('Total quantity to be distributed in dividends: {} {}'.format(util.value_out(db, dividend_total, dividend_asset), dividend_asset))

    if dividend_asset == config.BTC:
        return (source, [(output['address'], output['dividend_quantity']) for output in outputs], None)

    asset_id = util.get_asset_id(db, asset, util.CURRENT_BLOCK_INDEX)
    dividend_asset_id = util.get_asset_id(db, dividend_asset, util.CURRENT_BLOCK_INDEX)
    data = message_type.pack(ID)
    data += struct.pack(FORMAT_2, quantity_per_unit, asset_id, dividend_asset_id)
    return (source, [], data)

def parse (db, tx, message):
    dividend_parse_cursor = db.cursor()

    # Unpack message.
    try:
        if (tx['block_index'] > 288150 or config.TESTNET or config.REGTEST) and len(message) == LENGTH_2:
            quantity_per_unit, asset_id, dividend_asset_id = struct.unpack(FORMAT_2, message)
            asset = util.get_asset_name(db, asset_id, tx['block_index'])
            dividend_asset = util.get_asset_name(db, dividend_asset_id, tx['block_index'])
            status = 'valid'
        elif len(message) == LENGTH_1:
            quantity_per_unit, asset_id = struct.unpack(FORMAT_1, message)
            asset = util.get_asset_name(db, asset_id, tx['block_index'])
            dividend_asset = config.XCP
            status = 'valid'
        else:
            raise exceptions.UnpackError
    except (exceptions.UnpackError, exceptions.AssetNameError, struct.error) as e:
        dividend_asset, quantity_per_unit, asset = None, None, None
        status = 'invalid: could not unpack'

    if dividend_asset == config.BTC:
        status = 'invalid: cannot pay {} dividends within protocol'.format(config.BTC)

    if status == 'valid':
        # For SQLite3
        quantity_per_unit = min(quantity_per_unit, config.MAX_INT)

        dividend_total, outputs, problems, fee = validate(db, tx['source'], quantity_per_unit, asset, dividend_asset, block_index=tx['block_index'])
        if problems: status = 'invalid: ' + '; '.join(problems)
    else:
        fee = 0

    if status == 'valid':
        # Debit.
        util.debit(db, tx['source'], dividend_asset, dividend_total, action='dividend', event=tx['tx_hash'])
        if tx['block_index'] >= 330000 or config.TESTNET or config.REGTEST: # Protocol change.
            util.debit(db, tx['source'], config.XCP, fee, action='dividend fee', event=tx['tx_hash'])

        # Credit.
        for output in outputs:
            if not util.enabled('dont_credit_zero_dividend') or output['dividend_quantity'] > 0:
                util.credit(db, output['address'], dividend_asset, output['dividend_quantity'], action='dividend', event=tx['tx_hash'])

    # Add parsed transaction to message-type–specific table.
    bindings = {
        'tx_index': tx['tx_index'],
        'tx_hash': tx['tx_hash'],
        'block_index': tx['block_index'],
        'source': tx['source'],
        'asset': asset,
        'dividend_asset': dividend_asset,
        'quantity_per_unit': quantity_per_unit,
        'fee_paid': fee,
        'status': status,
    }

    if "integer overflow" not in status:
        sql = 'insert into dividends values(:tx_index, :tx_hash, :block_index, :source, :asset, :dividend_asset, :quantity_per_unit, :fee_paid, :status)'
        dividend_parse_cursor.execute(sql, bindings)
    else:
        if tx["block_index"] != config.MEMPOOL_BLOCK_INDEX:
            logger.warn("Not storing [dividend] tx [%s]: %s" % (tx['tx_hash'], status))
            logger.debug("Bindings: %s" % (json.dumps(bindings), ))

    dividend_parse_cursor.close()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
