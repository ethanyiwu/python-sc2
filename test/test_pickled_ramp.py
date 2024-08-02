"""
You can execute this test running the following command from the root python-sc2 folder:
poetry run pytest test/test_pickled_ramp.py

This test/script uses the pickle files located in "python-sc2/test/pickle_data" generated by "generate_pickle_files_bot.py" file, which is a bot that starts a game on each of the maps defined in the main function.

It will load the pickle files, recreate the bot object from scratch and tests most of the bot properties and functions.
All functions that require some kind of query or interaction with the API directly will have to be tested in the "autotest_bot.py" in a live game.
"""

import time
from pathlib import Path
from test.test_pickled_data import MAPS, get_map_specific_bot

from loguru import logger

from sc2.game_info import Ramp
from sc2.position import Point2
from sc2.unit import Unit
from sc2.units import Units


# From https://docs.pytest.org/en/latest/example/parametrize.html#a-quick-port-of-testscenarios
def pytest_generate_tests(metafunc):
    idlist = []
    argvalues = []
    for scenario in metafunc.cls.scenarios:
        idlist.append(scenario[0])
        items = scenario[1].items()
        argnames = [x[0] for x in items]
        argvalues.append(([x[1] for x in items]))
    metafunc.parametrize(argnames, argvalues, ids=idlist, scope="class")


class TestClass:
    # Load all pickle files and convert them into bot objects from raw data (game_data, game_info, game_state)
    scenarios = [(map_path.name, {"map_path": map_path}) for map_path in MAPS]

    def test_main_base_ramp(self, map_path: Path):
        bot = get_map_specific_bot(map_path)
        bot.game_info.map_ramps, bot.game_info.vision_blockers = bot.game_info._find_ramps_and_vision_blockers()

        # Test if main ramp works for all spawns
        for spawn in bot.game_info.start_locations + [bot.townhalls[0].position]:
            # Remove cached precalculated ramp
            if hasattr(bot, "main_base_ramp"):
                del bot.main_base_ramp

            # Set start location as one of the opponent spawns
            bot.game_info.player_start_location = spawn

            # Find main base ramp for opponent
            ramp: Ramp = bot.main_base_ramp
            assert ramp.top_center
            assert ramp.bottom_center
            assert ramp.size
            assert ramp.points
            assert ramp.upper
            assert ramp.lower
            # Test if ramp was detected far away
            logger.info(ramp.top_center)
            distance = ramp.top_center.distance_to(bot.game_info.player_start_location)
            assert (
                distance < 30
            ), f"Distance from spawn to main ramp was detected as {distance:.2f}, which is too far. Spawn: {spawn}, Ramp: {ramp.top_center}"
            # On the map HonorgroundsLE, the main base is large and it would take a bit of effort to fix, so it returns None or empty set
            if len(ramp.upper) in {2, 5}:
                assert ramp.upper2_for_ramp_wall
                # Check if terran wall was found
                assert ramp.barracks_correct_placement
                assert ramp.barracks_in_middle
                assert ramp.depot_in_middle
                assert len(ramp.corner_depots) == 2
                # Check if protoss wall was found
                assert ramp.protoss_wall_pylon
                assert len(ramp.protoss_wall_buildings) == 2
                assert ramp.protoss_wall_warpin
            else:
                # On maps it is unable to find valid wall positions (Honorgrounds LE) it should return None, empty sets or empty lists
                assert ramp.barracks_correct_placement is None
                assert ramp.barracks_in_middle is None
                assert ramp.depot_in_middle is None
                assert ramp.corner_depots == set()
                assert ramp.protoss_wall_pylon is None
                assert ramp.protoss_wall_buildings == frozenset()
                assert ramp.protoss_wall_warpin is None

    def test_bot_ai(self, map_path: Path):
        bot = get_map_specific_bot(map_path)

        # Recalculate and time expansion locations
        t0 = time.perf_counter()
        bot._find_expansion_locations()
        t1 = time.perf_counter()
        logger.info(f"Time to calculate expansion locations: {t1-t0} s")

        # TODO: Cache all expansion positions for a map and check if it is the same
        # BelShirVestigeLE has only 10 bases - perhaps it should be removed since it was a WOL / HOTS map
        assert len(bot.expansion_locations_list) >= 10, f"Too few expansions found: {len(bot.expansion_locations_list)}"
        # Honorgrounds LE has 24 bases
        assert (
            len(bot.expansion_locations_list) <= 24
        ), f"Too many expansions found: {len(bot.expansion_locations_list)}"
        # On N player maps, it is expected that there are N*X bases because of symmetry, at least for maps designed for 1vs1
        # Those maps in the list have an un-even expansion count
        expect_even_expansion_count = 1 if bot.game_info.map_name in ["StargazersAIE", "Stasis LE"] else 0
        assert (
            len(bot.expansion_locations_list) % (len(bot.enemy_start_locations) + 1) == expect_even_expansion_count
        ), f"{bot.expansion_locations_list}"
        # Test if bot start location is in expansion locations
        assert (
            bot.townhalls.random.position in set(bot.expansion_locations_list)
        ), f'This error might occur if you are running the tests locally using command "pytest test/", possibly because you are using an outdated cache.py version, but it should not occur when using docker and poetry.\n{bot.townhalls.random.position}, {bot.expansion_locations_list}'
        # Test if enemy start locations are in expansion locations
        for location in bot.enemy_start_locations:
            assert location in set(bot.expansion_locations_list), f"{location}, {bot.expansion_locations_list}"
        # Each expansion is supposed to have at least one geysir and 6-12 minerals
        for expansion, resource_positions in bot.expansion_locations_dict.items():
            assert isinstance(expansion, Point2)
            assert isinstance(resource_positions, Units)
            if resource_positions:
                assert isinstance(resource_positions[0], Unit)
            # 2000 Atmospheres has bases with just 4 minerals patches and a rich geysir
            # Neon violet has bases with just 6 resources. I think that was the back corner base with 4 minerals and 2 vespene
            # Odyssey has bases with 10 mineral patches and 2 geysirs
            # Blood boil returns 21?
            assert (
                5 <= len(resource_positions) <= 12
            ), f"{len(resource_positions)} resource fields in one base on map {bot.game_info.map_name}"

        assert bot.owned_expansions == {bot.townhalls.first.position: bot.townhalls.first}
