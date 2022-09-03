from __future__ import annotations

import typing

from ctc import binary
from ctc import spec
from . import gnosis_safe_spec


def parse_safe_signatures(
    signatures: spec.Data,
) -> typing.Sequence[typing.Mapping[str, typing.Any]]:
    """
    reference: https://docs.gnosis-safe.io/contracts/signatures
    """
    as_bytes = binary.convert(signatures, 'binary')

    eip_1271_positions = []
    eip_1271_indices = []
    s = 0
    parsed_signatures = []
    while True:
        signature = as_bytes[:65]
        as_bytes = as_bytes[65:]

        assert len(signature) == 65

        signature_type = signature[-1]
        if 31 > signature_type and signature_type > 26:
            parsed = {
                'type': 'ecdsa',
                'signature': binary.convert(signature, 'prefix_hex'),
                'r': binary.convert(signature[:32], 'integer'),
                's': binary.convert(signature[32:64], 'integer'),
                'v': binary.convert(signature_type, 'integer'),
            }
        elif signature_type > 30:
            parsed = {
                'type': 'eth_sign',
                'signature': binary.convert(signature, 'prefix_hex'),
                'r': binary.convert(signature[:32], 'integer'),
                's': binary.convert(signature[32:64], 'integer'),
                'v': binary.convert(signature_type - 4, 'integer'),
            }
        elif signature_type == 0:
            parsed = {
                'type': 'eip1271',
                'signature': binary.convert(signature, 'prefix_hex'),
                'verifier': binary.convert(signature[:32][-20:], 'prefix_hex'),
                'position': binary.convert(signature[32:64], 'integer'),
            }
            position: int = typing.cast(int, parsed['position'])
            eip_1271_positions.append(position)
            eip_1271_indices.append(s)
        elif signature_type == 1:
            parsed = {
                'type': 'prevalidated',
                'signature': binary.convert(signature, 'prefix_hex'),
                'validator': binary.convert(signature[:32][-20:], 'prefix_hex'),
            }
        else:
            raise Exception('unknown signature type: ' + str(signature_type))

        parsed_signatures.append(parsed)
        s += 1

        if len(as_bytes) == 0:
            break
        if len(eip_1271_positions) > 0 and s * 65 >= min(eip_1271_positions):
            break

    return parsed_signatures


def get_safe_transaction_signers(
    *,
    signatures: spec.BinaryData
    | typing.Sequence[typing.Mapping[str, typing.Any]],
    safe_transaction_hash: spec.Data,
    safe_transaction: gnosis_safe_spec.SafeTransaction,
    chain_id: int,
    safe_address: spec.Address,
    call_data: spec.Data,
    nonce: int,
) -> typing.Sequence[spec.Address]:

    if signatures is None:
        signatures = get_safe_signatures_from_call_data(call_data)

    if safe_transaction_hash is None:
        if (
            call_data is None
            or nonce is None
            or chain_id is None
            or safe_address is None
        ):
            raise Exception(
                'must specify safe_transaction_hash or {call_data, nonce, chain_id, safe_address}'
            )
        safe_transaction = get_safe_transaction_from_call_data(
            call_data=call_data,
            nonce=nonce,
        )
        safe_transaction_hash = hash_safe_transaction(
            safe_transaction=safe_transaction,
            chain_id=chain_id,
            safe_address=safe_address,
        )

    return _get_safe_transaction_signers(
        signatures=signatures,
        safe_transaction_hash=safe_transaction_hash,
    )


def _get_safe_transaction_signers(
    *,
    signatures: spec.BinaryData
    | typing.Sequence[typing.Mapping[str, typing.Any]],
    safe_transaction_hash: spec.Data,
) -> typing.Sequence[spec.Address]:

    if isinstance(signatures, list):
        parsed_signatures: typing.Sequence[
            typing.Mapping[str, typing.Any]
        ] = signatures
    elif isinstance(signatures, (str, bytes)):
        parsed_signatures = parse_safe_signatures(signatures)
    else:
        raise Exception('unknown signatures format: ' + str(type(signatures)))

    signers = []
    for signature in parsed_signatures:

        if signature['type'] in ['ecdsa', 'eth_sign']:
            vrs = signature['v'], signature['r'], signature['s']
            signer = binary.recover_signer_address(
                message_hash=safe_transaction_hash,
                signature=vrs,
            )
        elif signature['type'] == 'eip1271':
            signer = signature['verifier']
        elif signature['type'] == 'prevalidated':
            signer = signature['validator']
        else:
            raise Exception('unknown signature type: ' + str(signature['type']))

        signers.append(signer)

    return signers


def hash_safe_transaction(
    safe_transaction: gnosis_safe_spec.SafeTransaction,
    chain_id: int,
    safe_address: spec.Address,
) -> spec.Data:
    """compute the hash to be signed by safe owners"""

    domain = {
        'chain_id': chain_id,
        'verifying_contract': safe_address,
    }
    return binary.eip712_hash(
        struct_data=safe_transaction,
        struct_type=gnosis_safe_spec.safe_transaction_type,
        domain=domain,
    )


#
# # extracting data from call data
#


def get_safe_transaction_from_call_data(
    call_data: spec.BinaryData,
    nonce: int,
) -> gnosis_safe_spec.SafeTransaction:

    # decode transaction parameters
    decoded = binary.decode_call_data(
        call_data=call_data,
        function_abi=gnosis_safe_spec.function_abis['execTransaction'],
    )
    parameters = typing.cast(
        typing.Mapping[str, typing.Any], decoded['named_parameters']
    )

    # create safe transaction from decoded transaction parameters
    safe_transaction: gnosis_safe_spec.SafeTransaction = {  # type: ignore
        key: parameters[key]
        for key in gnosis_safe_spec.safe_transaction_keys
        if key != 'nonce'
    }
    safe_transaction['nonce'] = nonce
    return safe_transaction


def get_safe_signatures_from_call_data(
    call_data: spec.BinaryData,
) -> typing.Sequence[typing.Mapping[str, typing.Any]]:
    # decode transaction parameters
    decoded = binary.decode_call_data(
        call_data=call_data,
        function_abi=gnosis_safe_spec.function_abis['execTransaction'],
    )

    # return signatures
    parameters = typing.cast(
        typing.Mapping[str, typing.Any], decoded['named_parameters']
    )
    raw_signatures = parameters['signatures']
    return parse_safe_signatures(raw_signatures)