"""Bounded, deterministic linear through-service chains supported by CV v1."""

class ConnectionGraphError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def linear_chains(edges):
    forward, backward = {}, {}
    nodes = set()
    for incoming, outgoing in edges:
        if incoming == outgoing:
            raise ConnectionGraphError('connection_cycle', 'A service cannot connect back to itself.')
        if incoming in forward and forward[incoming] != outgoing or outgoing in backward and backward[outgoing] != incoming:
            raise ConnectionGraphError('connection_branch', 'Each service can have one preceding and one following connection. Review the existing link first.')
        forward[incoming] = outgoing
        backward[outgoing] = incoming
        nodes.update((incoming, outgoing))
    chains, visited = [], set()
    for head in sorted(nodes - set(backward), key=str):
        chain, current = [], head
        while current is not None:
            if current in visited:
                raise ConnectionGraphError('connection_cycle', 'Connections cannot form a loop.')
            visited.add(current);chain.append(current);current = forward.get(current)
        if len(chain) > 1:
            chains.append(tuple(chain))
    if len(visited) != len(nodes):
        raise ConnectionGraphError('connection_cycle', 'Connections cannot form a loop.')
    return tuple(chains)


def connection_day_issues(edges, trips, vehicle_types, transfers):
    """Use actual elapsed instants and verified transfers; never infer a missing duration."""
    result=[]
    for chain in linear_chains(edges):
        common=set(trips[chain[0]]['types'])
        for identifier in chain[1:]:common.intersection_update(trips[identifier]['types'])
        labels=' → '.join(trips[identifier]['trip_code'] for identifier in chain)
        if not common:
            result.append({'code':'connection_types_conflict','trip_code':labels,
                'message':'Linked services need a common eligible vehicle category.'})
        elif vehicle_types and not common.intersection(vehicle_types):
            result.append({'code':'connection_vehicle_required','trip_code':labels,'allowed_bus_types':sorted(common),
                'message':'Confirm one vehicle category that can operate all linked services.'})
        for incoming,outgoing in zip(chain,chain[1:]):
            first,second=trips[incoming],trips[outgoing]
            required=0 if first['destination']==second['origin'] else transfers.get((first['destination'],second['origin']))
            gap=second['start']-first['end']
            if gap<0 or required is not None and gap<required:
                result.append({'code':'connection_time_conflict','trip_code':first['trip_code']+' → '+second['trip_code'],
                    'message':'The following service leaves before the same vehicle can reach it on this service day.'})
    return result
