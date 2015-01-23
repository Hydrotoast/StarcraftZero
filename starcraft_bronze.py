import copy
import queue
from itertools import product


MAX_DRONES = 50
MAX_OVERLORDS = 25

# Heuristics
UNITS_PER_OVERLORD = 4
#DRONES_PER_HATCHERY = 16

# Cache of the states
cache = set()


class State:
    def __init__(self):
        # Ordinal states
        self.hatcheries = 1
        self.drones = 5
        self.zerglings = 0
        self.overlords = 1

        # Required to produce zerglings
        self.has_spawning_pool = False

    @property
    def units(self):
        return self.drones + self.zerglings

    @property
    def food_cap(self):
        return 8 * self.overlords

    @property
    def minerals_per_second(self):
        return 8 * self.drones

    @property
    def max_units_producible(self):
        return min(self.hatcheries,
                   self.food_cap - self.units)

    @property
    def max_buildings_producible(self):
        return self.drones - 1

    @property
    def max_drones_producible(self):
        return min(self.max_units_producible,
                   MAX_DRONES - self.drones)

    @property
    def max_overlords_producible(self):
        return min(self.max_units_producible,
                   min(self.units // UNITS_PER_OVERLORD + 1, MAX_OVERLORDS) - self.overlords)

    @property
    def max_zerglings_producible(self):
        return self.max_units_producible if self.has_spawning_pool else 0

    @property
    def max_hatcheries_producible(self):
        return self.max_buildings_producible
        #return min(self.max_buildings_producible
        #           self.drones // DRONES_PER_HATCHERY + 1 - self.hatcheries)

    @property
    def is_end_state(self):
        return self.zerglings >= 150

    def evaluate(self):
        return -(self.drones + self.hatcheries + self.overlords + self.zerglings + self.has_spawning_pool)

    def __lt__(self, other):
        return self.evaluate() - other.evaluate()

    def __hash__(self):
        return self.drones << 24 \
            + self.zerglings << 16 \
            + self.overlords << 12 \
            + self.hatcheries << 8 \
            + self.has_spawning_pool

    def __eq__(self, other):
        return isinstance(other, State) \
            and self.hatcheries == other.hatcheries \
            and self.drones == other.drones \
            and self.overlords == other.overlords \
            and self.zerglings == other.zerglings \
            and self.has_spawning_pool == other.has_spawning_pool

    def __str__(self):
        return "State(hatcheries={}, drones={}, zerglings={}, overlords={}, has_spawning_pool={})".format(
            self.hatcheries, self.drones, self.zerglings, self.overlords, self.has_spawning_pool)


class MineralCost:
    HATCHERY = 450
    DRONE = 50
    OVERLORD = 100
    ZERG = 50
    SPAWNING_POOL = 200


class HatcheryProduction:
    def __init__(self, drones: int, overlords: int, zerglings: int):
        self.drones = drones
        self.overlords = overlords
        self.zerglings = zerglings

    def minerals_needed(self):
        minerals_needed = 0
        minerals_needed += MineralCost.DRONE * self.drones
        minerals_needed += MineralCost.OVERLORD * self.overlords
        minerals_needed += MineralCost.ZERG * self.zerglings
        return minerals_needed

    @property
    def time_needed(self):
        return self.drones + self.overlords + self.zerglings


class DroneProduction:
    def __init__(self, hatcheries: int, spawning_pool: bool):
        self.hatcheries = hatcheries
        self.spawning_pool = spawning_pool

    def minerals_needed(self, state: State):
        minerals_needed = 0
        minerals_needed += MineralCost.HATCHERY * self.hatcheries
        minerals_needed += MineralCost.SPAWNING_POOL if not state.has_spawning_pool and self.spawning_pool else 0
        return minerals_needed

    @property
    def time_needed(self):
        return 0


def hatchery_productions(state: State) -> [HatcheryProduction]:
    """
    Generates a set of possible productions from hatcheries
    :param state: Current state of the game
    :return: A generator of the set of possible productions from hatcheries
    """
    drones_producible = range(state.max_drones_producible + 1)
    overlords_producible = range(state.max_overlords_producible + 1)
    zerglings_producible = range(state.max_zerglings_producible + 1)

    prods = []
    for drones, overlords, zerglings in product(drones_producible, overlords_producible, zerglings_producible):
        if drones + zerglings <= state.max_units_producible:
            prods.append(HatcheryProduction(drones, overlords, zerglings))
    return prods


def drone_productions(state: State) -> [DroneProduction]:
    """
    Generates a set of possible productions from drones.
    :param state: Current state of the game
    :return: A generator of the set of possible productions from drones
    """
    hatcheries_producible = range(state.max_hatcheries_producible + 1)
    spawning_pool_producible = [False] if state.has_spawning_pool else [True, False]

    prods = []
    for hatcheries, spawning_pool in product(hatcheries_producible, spawning_pool_producible):
        if hatcheries + spawning_pool <= state.max_buildings_producible:
            prods.append(DroneProduction(hatcheries, spawning_pool))
    return prods


def productions(drone_prods: [DroneProduction], hatchery_prods: [HatcheryProduction]) \
        -> [(DroneProduction, HatcheryProduction)]:
    """
    Generates a pair of productions from drones and hatcheries.
    :param drone_prods: A generator of possible drone productions
    :param hatchery_prods: A generator of possible hatchery productions
    :return: A generator of the cross product of productions over drones and hatcheries
    """
    for drone_prod, hatchery_prod in product(drone_prods, hatchery_prods):
        if drone_prod.hatcheries + drone_prod.spawning_pool > 0 \
                or hatchery_prod.drones + hatchery_prod.overlords + hatchery_prod.zerglings > 0:
            yield drone_prod, hatchery_prod


def next_state(state: State, hatchery_prod: HatcheryProduction, drone_prod: DroneProduction) -> (int, State):
    """
    Builds the next state given a current state, a choice of the hatchery production, and a choice of the drone
    production.
    :param state: Current state of the game
    :param hatchery_prod: Hatchery production choice
    :param drone_prod: Drone production choice
    :return: A pair of a waiting time and state
    """
    new_state = copy.copy(state)
    minerals_needed = hatchery_prod.minerals_needed() + drone_prod.minerals_needed(state)

    new_state.drones += hatchery_prod.drones
    new_state.overlords += hatchery_prod.overlords
    new_state.zerglings += hatchery_prod.zerglings

    new_state.hatcheries += drone_prod.hatcheries
    new_state.drones -= drone_prod.hatcheries
    new_state.drones -= 1 if not state.has_spawning_pool and drone_prod.spawning_pool else 0
    new_state.has_spawning_pool = state.has_spawning_pool or drone_prod.spawning_pool

    wait_time = minerals_needed / state.minerals_per_second + hatchery_prod.time_needed + drone_prod.time_needed
    return wait_time, new_state


def next_states(state: State) -> [(int, State)]:
    """
    Generates the next states of a given state.
    :param state: Current state of the game
    :return: A generator of pairs of waiting times to the next states of a given state
    """
    for drone_prod, hatchery_prod in productions(drone_productions(state), hatchery_productions(state)):
        wait_time, new_state = next_state(state, hatchery_prod, drone_prod)
        if new_state not in cache:
            cache.add(new_state)
            yield wait_time, new_state


def shortest_path_to_goal(start: State):
    """
    Executes dijkstra through the game tree until the goal state is found. The ending time and state are printed at
    the end of the algorithm.
    :param start: Current state of the game
    """
    pq = queue.PriorityQueue()
    pq.put((0.0, start))
    while not pq.empty():
        time, current_state = pq.get()

        # Print integer progress
        if time.is_integer():
            print("{:.2f}: {}".format(time, current_state))

        # Check endgame
        if current_state.is_end_state:
            print("Time to at least 150 Zerglings: {:.2f}".format(time))
            print("State: {}".format(current_state))
            break

        # Add next game states to frontier
        for wait_time, state in next_states(current_state):
            pq.put((time + wait_time, state))


def main():
    start = State()
    shortest_path_to_goal(start)


if __name__ == '__main__':
    main()