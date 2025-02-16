import unittest

from core import *
from characters import *
from info import *


def assert_solutions(
	testcase: unittest.TestCase, 
	worlds: Generator[State],
	solutions: tuple[tuple[Character, ...]],
):
	"""
	Checks that a given list of world states has character placements that 
	exactly match the allowed solutions
	"""
	def to_string(answer: Iterable[Character]) -> str:
		return ', '.join(x.__name__ for x in answer)
	predictions = tuple(
		to_string(world.initial_characters)
		for world in worlds
	)
	testcase.assertEqual(sorted(predictions), sorted(map(to_string, solutions)))


class Puzzles(unittest.TestCase):
	def test_puzzle_1(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1erb5e2/can_the_sober_savant_solve_the_puzzle

		You, Tim, Sula, Oscar, Matt, Anna = range(6)

		class DrunkBetweenTownsfolk(Info):
			def __call__(self, state: State, src: PlayerID):
				N = len(state.players)
				result = FALSE
				for i, player in enumerate(state.players):
					found_drunk = IsCharacter(i, Drunk)(state, src)
					if found_drunk is FALSE:
						continue
					tf_neighbours = (
						IsCategory((i - 1) % N, TOWNSFOLK)(state, src) & 
						IsCategory((i + 1) % N, TOWNSFOLK)(state, src)
					)
					result |= found_drunk & tf_neighbours
				return result

		state = State([
			Player(name='You', character=Savant(day_actions={
				0: Savant.Ping(
					IsInPlay(Investigator), 
					IsEvil(Tim) | IsEvil(Anna)
				),
				1: Savant.Ping(
					Chef.Ping(1), 
					DrunkBetweenTownsfolk()
				),
				2: Savant.Ping(
					IsCategory(Tim, MINION) | IsCategory(Sula, MINION),
					~IsInPlay(Noble)
				),
			})),
			Player(name='Tim', character=Knight(night_actions={
				0: Knight.Ping(Sula, Anna)
			})),
			Player(name='Sula', character=Steward(night_actions={
				0: Steward.Ping(Matt)
			})),
			Player(name='Oscar', character=Investigator(night_actions={
				0: Investigator.Ping(Sula, Anna, Goblin)
			})),
			Player(name='Matt', character=Noble(night_actions={
				0: Noble.Ping(Tim, Sula, Oscar)
			})),
			Player(name='Anna', character=Seamstress(night_actions={
				0: Seamstress.Ping(Sula, Oscar, same=False)
			}))
		])

		worlds = world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[Drunk],
			possible_hidden_self=[],
			category_counts=(3, 1, 1, 1), # townsfolk outsiders minions demons
		)

		assert_solutions(self, worlds, solutions=(
			(Savant, Goblin, Steward, Drunk, Noble, Leviathan),
		))


	def test_puzzle_2(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1ewxu0r/weekly_puzzle_2_come_fly_with_me/

		You, Steph, Fraser, Tim, Sarah, Matthew, Anna, Sula = range(8)
		state = State([
			Player(name='You', character=Seamstress(night_actions={
				0: Seamstress.Ping(Matthew, Sula, same=True)
			})),
			Player(name='Steph', character=Knight(night_actions={
				0: Knight.Ping(Tim, Sula)
			})),
			Player(name='Fraser', character=FortuneTeller(night_actions={
				0: FortuneTeller.Ping(Sarah, Anna, demon=False),
				1: FortuneTeller.Ping(You, Fraser, demon=False),
				2: FortuneTeller.Ping(Steph, Sarah, demon=False),
			})),
			Player(name='Tim', character=Saint()),
			Player(name='Sarah', character=Investigator(night_actions={
				0: Investigator.Ping(Matthew, Fraser, Goblin)
			})),
			Player(name='Matthew', character=Juggler(
				day_actions={
					0: Juggler.Juggle({
						Steph: Knight,
						Sarah: Leviathan,
						Anna: Goblin,
						Sula: Goblin,
						You: Seamstress,
					})
				},
				night_actions={
					1: Juggler.Ping(2)
				}
			)),
			Player(name='Anna', character=Clockmaker(night_actions={
				0: Clockmaker.Ping(1)
			})),
			Player(name='Sula', character=Balloonist(night_actions={
				0: Balloonist.Ping(Tim),
				1: Balloonist.Ping(Matthew),
				2: Balloonist.Ping(Steph),
			})),
		])


		worlds = world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[Drunk],
			possible_hidden_self=[Drunk],
			category_counts=(5, 1, 1, 1), # townsfolk, outsiders, minions, demons
		)

		assert_solutions(self, worlds, solutions=(
			(Drunk, Knight, FortuneTeller, Saint, Goblin, 
				Leviathan, Clockmaker, Balloonist),
		))


	def test_puzzle_5a(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1fcriex/weekly_puzzle_5a_5b_you_only_guess_twice/

		You, Dan, Tom, Matt, Anna, Hannah, Oscar = range(7)
		state = State([
			Player(name='You', character=Alsaahir()),
			Player(name='Dan', character=Noble(night_actions={
				0: Noble.Ping(Tom, Anna, Hannah)
			})),
			Player(name='Tom', character=Knight(night_actions={
				0: Knight.Ping(Dan, Anna)
			})),
			Player(name='Matt', character=Investigator(night_actions={
				0: Investigator.Ping(Anna, Oscar, Goblin)
			})),
			Player(name='Anna', character=Empath(night_actions={
				0: Empath.Ping(Dan)
			})),
			Player(name='Hannah', character=Steward(night_actions={
				0: Steward.Ping(Tom)
			})),
			Player(name='Oscar', character=Seamstress(night_actions={
				0: Seamstress.Ping(Tom, Hannah, same=False)
			})),
		])

		worlds = world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[],
			possible_hidden_self=[],
			category_counts=(5, 0, 1, 1), # townsfolk outsiders minions demons
		)

		assert_solutions(self, worlds, solutions=(
			(Alsaahir, Noble, Knight, Investigator, Empath, Leviathan, Goblin),
			(Alsaahir, Noble, Knight, Investigator, Goblin, Steward, Leviathan),
		))



	def test_puzzle_5b(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1fcriex/weekly_puzzle_5a_5b_you_only_guess_twice/

		You, Sarah, Tim, Matthew, Steph, Aoife, Fraser = range(7)
		state = State([
			Player(name='You', character=Juggler()),
			Player(name='Sarah', character=Empath(night_actions={
				0: Empath.Ping(You)
			})),
			Player(name='Tim', character=Seamstress(night_actions={
				0: Seamstress.Ping(You, Fraser, same=True)
			})),
			Player(name='Matthew', character=Steward(night_actions={
				0: Steward.Ping(You)
			})),
			Player(name='Steph', character=Investigator(night_actions={
				0: Investigator.Ping(Sarah, Fraser, Goblin)
			})),
			Player(name='Aoife', character=Noble(night_actions={
				0: Noble.Ping(Sarah, Tim, Matthew)
			})),
			Player(name='Fraser', character=Knight(night_actions={
				0: Knight.Ping(You, Steph)
			})),
		])

		worlds = world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[],
			possible_hidden_self=[],
			category_counts=(5, 0, 1, 1), # townsfolk outsiders minions demons
		)

		assert_solutions(self, worlds, solutions=(
			(Juggler, Leviathan, Seamstress, Steward, Goblin, Noble, Knight),
			(Juggler, Empath, Seamstress, Leviathan, Goblin, Noble, Knight),
			(Juggler, Goblin, Seamstress, Steward, Investigator, Leviathan, Knight),
			(Juggler, Empath, Seamstress, Steward, Goblin, Leviathan, Knight),
		))


	def test_puzzle_7(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1foeq4d/weekly_puzzle_7_the_savant_strikes_back/

		You, Fraser, Sarah, Oscar, Anna, Aoife, Steph, Tim = range(8)

		state = State([
			Player(name='You', character=Savant(day_actions={
				0: Savant.Ping(
					ExactlyN(N=1, args=[IsEvil(Fraser), IsEvil(Anna), IsEvil(Steph)]),
					Clockmaker.Ping(3),
				),
				1: Savant.Ping(
					CharAttrEq(Sarah, 'red_herring', Sarah),
					CharAttrEq(Fraser, 'is_drunk_VI', True),
				),
				2: Savant.Ping(
					ExactlyN(N=2, args=[
						IsInPlay(Juggler),
						IsInPlay(Shugenja),
						IsInPlay(VillageIdiot)
					]),
					ExactlyN(N=2, args=[
						IsCategory(Oscar, TOWNSFOLK),
						IsCategory(Anna, TOWNSFOLK),
						IsCategory(Tim, TOWNSFOLK)
					]),
				),
			})),
			Player(name='Fraser', character=VillageIdiot(night_actions={
				0: VillageIdiot.Ping(Sarah, is_evil=False),
				1: VillageIdiot.Ping(Aoife, is_evil=False),
				2: VillageIdiot.Ping(You, is_evil=False),
			})),
			Player(name='Sarah', character=FortuneTeller(night_actions={
				0: FortuneTeller.Ping(Oscar, Aoife, demon=False),
				1: FortuneTeller.Ping(You, Sarah, demon=True),
				2: FortuneTeller.Ping(Fraser, Tim, demon=False),
			})),
			Player(name='Oscar', character=Investigator(night_actions={
				0: Investigator.Ping(Fraser, Steph, Goblin),
			})),
			Player(name='Anna', character=Juggler(
				day_actions={0: Juggler.Juggle({You: Savant, Tim: VillageIdiot})},
				night_actions={1: Juggler.Ping(1)}
			)),
			Player(name='Aoife', character=Shugenja(night_actions={
				0: Shugenja.Ping(clockwise=False)
			})),
			Player(name='Steph', character=Dreamer(night_actions={
				0: Dreamer.Ping(Sarah, FortuneTeller, Leviathan),
				1: Dreamer.Ping(You, Savant, Goblin),
				2: Dreamer.Ping(Fraser, Mutant, Goblin),
			})),
			Player(name='Tim', character=VillageIdiot(night_actions={
				0: VillageIdiot.Ping(Anna, is_evil=False),
				1: VillageIdiot.Ping(Sarah, is_evil=False),
				2: VillageIdiot.Ping(You, is_evil=False),
			})),
		])

		worlds = list(world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[Mutant],
			possible_hidden_self=[],
			category_counts=(5, 1, 1, 1), # townsfolk, outsiders, minions, demons
		))

		assert_solutions(self, worlds, solutions=(
			(Savant, VillageIdiot, FortuneTeller, Goblin, 
				Leviathan, Shugenja, Mutant, VillageIdiot),
		))



	def test_puzzle_21(self):
		# https://www.reddit.com/r/BloodOnTheClocktower/comments/1hpqhai/weekly_puzzle_21_eight_jugglers_juggling/

		You, Fraser, Aoife, Josh, Tim, Matt, Olivia, Oscar = range(8)

		state = State([
			Player(name='You', character=Juggler(
				day_actions={0: Juggler.Juggle({Matt: Goblin, Oscar: Goblin})},
				night_actions={1: Juggler.Ping(0)},
			)),
			Player(name='Fraser', character=Juggler(
				day_actions={0: Juggler.Juggle({Olivia: Juggler, Oscar: Drunk})},
				night_actions={1: Juggler.Ping(1)},
			)),
			Player(name='Aoife', character=Juggler(
				day_actions={0: Juggler.Juggle({Olivia: Leviathan, Oscar: Leviathan})},
				night_actions={1: Juggler.Ping(0)},
			)),
			Player(name='Josh', character=Juggler(
				day_actions={0: Juggler.Juggle({Tim: Goblin, Oscar: Juggler})},
				night_actions={1: Juggler.Ping(1)},
			)),
			Player(name='Tim', character=Juggler(
				day_actions={0: Juggler.Juggle({You: Leviathan, Josh: Juggler})},
				night_actions={1: Juggler.Ping(0)},
			)),
			Player(name='Matt', character=Juggler(
				day_actions={0: Juggler.Juggle({Josh: Goblin, Tim: Juggler})},
				night_actions={1: Juggler.Ping(0)},
			)),
			Player(name='Olivia', character=Juggler(
				day_actions={0: Juggler.Juggle({You: Juggler, Aoife: Drunk})},
				night_actions={1: Juggler.Ping(2)},
			)),
			Player(name='Oscar', character=Juggler(
				day_actions={0: Juggler.Juggle({Josh: Goblin, Matt: Juggler})},
				night_actions={1: Juggler.Ping(0)},
			)),
		])

		worlds = list(world_gen(
			state,
			possible_demons=[Leviathan],
			possible_minions=[Goblin],
			possible_hidden_good=[Drunk],
			possible_hidden_self=[Drunk],
			category_counts=(5, 1, 1, 1), # townsfolk, outsiders, minions, demons
		))

		assert_solutions(self, worlds, solutions=(
			(Juggler, Juggler, Drunk, Juggler, Goblin, 
				Juggler, Juggler, Leviathan),
		))
