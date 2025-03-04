from __future__ import annotations

from dataclasses import dataclass, field
import enum
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
	from core import State, StateGen, Player
	from info import PlayerID, Info, STBool

import info
import events


"""
Implementing a Character Checklist:
 - Copying some other similar-ish character is likely a good starting point.
 - For a basic info characters, just create a Ping class inheriting from 
   info.Info and implement the __call__ method.
 - For more complex characters, or characters who have to make choices that are
   not evidenced by a Ping, override the relevant character methods such as
   [modify_category_counts, run_night/day/setup, killed, executed, etc.].
 - When overriding the default methods for complex characters, remember to 
   consider the desired behaviour of the new character if they are:
    - dead
	- droisoned
	- not their usual alignment
	- not the character who gets their claimed ping (Some TODO!)
	- spent
	- vortoxed
 - Remember to set `character.spent` or (TODO) call `state.chose(target)`
   appropriately and curse the Chambermaid / Goon for forcing that mental 
   burden on us.
"""


class Categories(enum.Enum):
	Townsfolk = enum.auto()
	Outsider = enum.auto()
	Minion = enum.auto()
	Demon = enum.auto()
	Traveller = enum.auto()

TOWNSFOLK = Categories.Townsfolk
OUTSIDER = Categories.Outsider
MINION = Categories.Minion
DEMON = Categories.Demon

type CategoryBounds = tuple[
	tuple[int, int],  # Townsfolk count min / max
	tuple[int, int],  # Outsiders count min / max
	tuple[int, int],  # Minions count min / max
	tuple[int, int],  # Demons count min / max
]

DEFAULT_CATEGORY_COUNTS = {
	5: (3, 0, 1, 1),
	6: (3, 1, 1, 1),
	7: (5, 0, 1, 1),
	8: (5, 1, 1, 1),
	9: (5, 2, 1, 1),
	10: (7, 0, 2, 1),
	11: (7, 1, 2, 1),
	12: (7, 2, 2, 1),
	13: (9, 0, 3, 1),
	14: (9, 1, 3, 1),
	15: (9, 2, 3, 1),
}

# Rules for when a player can legally ping and what the Chambermaid should see.
# Characters using MANUAL are responsible for rejecting worlds where pings are 
# not on legal nights.
class WakePattern(enum.Enum):
	NEVER = enum.auto()
	FIRST_NIGHT = enum.auto()
	EACH_NIGHT = enum.auto()
	EACH_NIGHT_STAR = enum.auto()
	EACH_NIGHT_UNTIL_SPENT = enum.auto()
	MANUAL = enum.auto()


@dataclass
class Character:

	# Characters like Recluse and Spy override here
	misregister_categories: ClassVar[tuple[Categories, ...]] = ()

	effects_active: bool = False

	# Night the character was created, usually 1
	first_night: int = 1

	@staticmethod
	def modify_category_counts(bounds: CategoryBounds) -> CategoryBounds:
		"""
		Modify bounds of acceptable character counts. E.g. the Baron should 
		override this method to increase the Outsider Min & Max and decrease
		the Townsfolk Min & Max. Meanwhile the Balloonist should increment only 
		the Outsider Max and decrement only the Townsfolk Min.
		"""
		return bounds

	def run_setup(self, state: State, player: PlayerID) -> StateGen:
		"""
		Create plausible worlds from the character's setup. E.g. the 
		Fortune Teller creates one world per choice of red herring. The 
		Marionette should just return (yield no candidate worlds) if it is not 
		sat next to the demon.
		"""
		raise NotImplementedError()

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:	
		"""
		Take the character's night action. Most basic info roles can just 
		inherit this default implementation and implement their own Pings to go
		in night_info.
		"""	
		if self.default_info_check(
			state, state.players[me].night_info, night, me
		):
			yield state

	def run_day(self, state: State, day: int, me: PlayerID) -> StateGen:
		if self.default_info_check(state, state.players[me].day_info, day, me):
			yield state

	def end_day(self, state: State, day: int, me: PlayerID) -> bool:
			"""
			Take dusk actions (e.g. poisoner stops poisoning).
			Can return False to invalidate the world, e.g., Vortox uses this to 
			reject worlds with no executions.
			"""
			return True

	def default_info_check(
		self: Character, 
		state: State,
		all_info: dict[int, Info],
		info_index: int, 
		me: PlayerID,
		even_if_dead: bool = False,
	) -> bool:
		"""Most info roles can reuse this pattern to run all their functions."""
		player = state.players[me]
		ping = all_info.get(info_index, None)
		if ping is None or player.is_evil or self.is_liar:
			return True
		if player.is_dead and not even_if_dead:
			return False

		is_vortox = state.vortox and (self.category is TOWNSFOLK)
		# We only ignore droisoned info if non-vortox worlds.
		if player.droison_count and not is_vortox:
			return True
		if is_vortox:
			return ping(state, me) is not info.TRUE
		return ping(state, me) is not info.FALSE

	def maybe_activate_effects(self, state: State, me: PlayerID) -> None:
		"""
		Effects that this character is having on other players. Needs to be 
		triggerable under one method so that e.g. a poisoner dying at night can
		reactivate that poisoner's current victim.
		If a character doesn't want this wrapper logic, it can override this 
		method rather than the _impl method.
		"""
		if (
			not self.effects_active
			and state.players[me].droison_count == 0
			and not state.players[me].is_dead
		):
			self.effects_active = True
			self._activate_effects_impl(state, me)

	def maybe_deactivate_effects(self, state: State, me: PlayerID) -> None:
		"""
		Will be called on any character at the moment they are poisoned, killed,
		or changed into another character.
		"""
		if self.effects_active:
			self.effects_active = False
			self._deactivate_effects_impl(state, me)

	def _activate_effects_impl(self, state: State, me: PlayerID) -> None:
		"""Individual character effect implementations override here."""
		pass
	def _deactivate_effects_impl(self, state: State, me: PlayerID) -> None:
		"""Individual character effect implementations override here."""
		pass

	def _apply_death(self, state: State, me: PlayerID) -> StateGen:
		"""Trigger consequences of a confirmed death."""
		state.players[me].is_dead = True
		self.maybe_deactivate_effects(state, me)
		yield from state.death_in_town(me)

	def attacked_at_night(
		self: Character,
	 	state: State,
	 	me: PlayerID,
	 	src: PlayerID,
	 ) -> StateGen:
		"""
		Called when attacked at night, decides whether this causes death or not.
		Remember to re-read the attacker properties on the yielded state in the
		calling method, because e.g. the Goon will create a state where the
		attacker has become drunk.
		"""
		if (
			state.players[me].is_dead 
			or self.cant_die(state, me)
			or (
				state.players[src].character.category is DEMON
				and getattr(state.players[me], 'safe_from_demon_count', 0)
			)
		):
			yield state
		else:
			yield from self._apply_death(state, me)

	def executed(self, state: State, me: PlayerID, died: bool) -> StateGen:
		"""Goblin, Psychopath, Saint etc override this method."""
		if died:
			yield from self.killed(state, me)
		elif self.cant_die(state, me):
			yield state

	def killed(self, state: State, me: PlayerID) -> StateGen:
		"""Check the death is logically valid, then apply it."""
		if not self.cant_die(state, me) and not state.players[me].is_dead:
			yield from self._apply_death(state, me)

	def cant_die(self, state: State, me: PlayerID) -> bool:
		"""Things like checking for innkeeper protection will go here :)"""
		return False

	def _world_str(self, state: State) -> str:
		"""
		For printing nice output representations of worlds. E.g 
		E.g. see Posoiner or Fortune Teller.
		"""
		return type(self).__name__


@dataclass
class Alsaahir(Character):
	"""Not yet implemented"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

@dataclass
class Balloonist(Character):
	"""
	Each night, you learn a player of a different character type than last night
	[+0 or +1 Outsider]
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	# Records the categories the last ping could have been registering as.
	prev_character: type[Character] = None 

	@staticmethod
	def modify_category_counts(bounds: CategoryBounds) -> CategoryBounds:
		(min_tf, max_tf), (min_out, max_out), mn, dm = bounds
		bounds = (min_tf - 1, max_tf), (min_out, max_out + 1), mn, dm
		return bounds

	@dataclass
	class Ping:  # Not info.Info because it doesn't implement __call__!
		player: PlayerID

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		"""
		Override Reason: even though we don't need to assert the balloonist 
		gets correct info when poisoned, we still need to take the action to 
		record that the following day the balloonist may see anything.

		NOTE: this implementation has only 1 day of memory, but technically the
		validity of balloonist pings can depend on all previous pings.
		E.g. a ping on 'Goblin, Legion, Imp' is not valid because legion must 
		have registered as one of minion or demon. I will fix this properly if 
		it ever actually comes up :)
		"""
		balloonist = state.players[me]
		ping = balloonist.night_info.get(night, None)
		if (
			balloonist.is_dead
			or balloonist.is_evil
			or ping is None
		):
			self.prev_character = None
			yield state; return

		character = type(state.players[ping.player].character)

		prev_character = self.prev_character
		self.prev_character = character
		if prev_character is None or balloonist.droison_count:
			# Just record todays ping to check tomorrow's validity
			yield state; return

		if state.vortox:
			# Balloonist MUST get the same category every night in vortox worlds
			if character.category is prev_character.category:
				yield state
			return

		same = info.SameCategory(character, prev_character)(state, me)
		if same is not info.TRUE:
			yield state


@dataclass
class Baron(Character):
	"""
	There are extra Outsiders in play. [+2 Outsiders]
	"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	@staticmethod
	def modify_category_counts(bounds: CategoryBounds) -> CategoryBounds:
		(min_tf, max_tf), (min_out, max_out), mn, dm = bounds
		bounds = (min_tf - 2, max_tf - 2), (min_out + 2, max_out + 2), mn, dm
		return bounds

@dataclass
class Chambermaid(Character):
	"""
	Each night, choose 2 alive players (not yourself):
	you learn how many woke tonight due to their ability.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		count: int
		def __call__(self, state: State, src: PlayerID) -> STBool:
			valid_choices = (
				self.player1 != src and self.player2 != src 
				and info.IsAlive(self.player1)(state, src) is not info.FALSE
				and info.IsAlive(self.player2)(state, src) is not info.FALSE
			)
			wake_count = (
				state.players[self.player1].woke_tonight +
				state.players[self.player2].woke_tonight
			)
			return info.STBool(valid_choices and wake_count == self.count)

def record_if_player_woke_tonight(state: State, pid: PlayerID) -> None:
	# Special cases not yet implemented:
	# - Chambermaid doesn't wake if there aren't valid choices
	# - Demon doesn't wake to on ability when exorcised
	player = state.players[pid]
	character = player.character
	match character.wake_pattern:
		case WakePattern.NEVER | WakePattern.MANUAL:
			woke = False
		case WakePattern.FIRST_NIGHT:
			woke = state.night == character.first_night
		case WakePattern.EACH_NIGHT:
			woke = True
		case WakePattern.EACH_NIGHT_STAR:
			woke = state.night != character.first_night
		case WakePattern.EACH_NIGHT_UNTIL_SPENT:
			woke = not character.spent
		case _:
			raise ValueError(
				f'{type(character).__name__} has {character.wake_pattern=}'
			)
	if woke and not player.is_dead:
		player.woke()

@dataclass
class Chef(Character):
	"""
	You start knowing how many pairs of evil players there are.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		count: int
		def __call__(self, state: State, src: PlayerID) -> STBool:
			N = len(state.players)
			trues, maybes = 0, 0
			evils = [info.IsEvil(i)(state, src) for i in range(N)]
			evils += [evils[0]]  # So that the following zip wraps the circle
			for a, b in zip(evils[:-1], evils[1:]):
				pair = a & b
				maybes += pair is info.MAYBE
				trues += pair is info.TRUE
			return info.STBool(trues <= self.count <= trues + maybes)

@dataclass
class Clockmaker(Character):
	"""
	You start knowing how many steps from the Demon to its nearest Minion.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		steps: int
		def __call__(self, state: State, src: PlayerID) -> STBool:
			"""
			This implementation checks against the min distance over all 
			minion-demon pairs, giving MAYBEs as appropriate. The phrase 
			"The Demon" must give living demons priority over dead demons, so if 
			there are any living demons, all dead demons are ignored.
			"""
			players = state.players
			N = len(players)
			minions, demons = (
				list(filter(
					lambda x: x[1] is not info.FALSE,
					[(i, info.IsCategory(i, cat)(state, src)) for i in range(N)]
				))
				for cat in (MINION, DEMON)
			)
			ignore_dead_demons = any(not players[i].is_dead for i, _ in demons)

			correct_distance, too_close = info.FALSE, info.FALSE
			for demon_pos, is_demon in demons:
				if players[demon_pos].is_dead and ignore_dead_demons:
					continue
				for minion_pos, is_minion in minions:
					is_pair = is_demon & is_minion
					distance = info.circle_distance(minion_pos, demon_pos, N)
					if distance < self.steps:
						too_close |= is_pair
					elif distance == self.steps:
						correct_distance |= is_pair

			return correct_distance & ~too_close

@dataclass
class Courtier(Character):
	"""
	Once per game, at night, choose a character:
	they are drunk for 3 nights & 3 days.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_UNTIL_SPENT

	target: PlayerID = None
	choice_night: int | None = None
	spent: bool = False

	@dataclass
	class Choice:
		character: type[Character]

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		courtier = state.players[me]
		if courtier.is_evil:
			# Yield all choices like a poisoner, plus the non-choice
			raise NotImplementedError("Todo: Evil Courtier")

		choice = courtier.night_info.get(night, None)
		if choice is None:
			yield state; return
		if courtier.is_dead or self.spent:
			return  # Drinking when spent or dead is a lie
		self.choice_night = night
		self.spent = True
		if courtier.droison_count:
			yield state; return  # Shame!

		for target in range(len(state.players)):
			hit = info.IsCharacter(target, choice.character)(state, me)
			if hit is info.FALSE:
				continue
			new_state = state.fork()
			new_courtier = new_state.players[me].character
			new_courtier.target = target
			new_courtier.maybe_activate_effects(new_state, me)
			yield new_state

	def end_day(self, state: State, day: int, me: PlayerID) -> bool:
		if self.target is not None and (day - self.choice_night) >= 2:
			self.maybe_deactivate_effects(state, me)
			self.target = None
		return True

	def _activate_effects_impl(self, state: State, me: PlayerID):
		if self.target == me:
			state.players[me].droison_count += 1
		elif self.target is not None:
			state.players[self.target].droison(state, me)

	def _deactivate_effects_impl(self, state: State, me: PlayerID):
		if self.target == me:
			state.players[me].droison_count -= 1
		elif self.target is not None:
			state.players[self.target].undroison(state, me)

@dataclass
class Dreamer(Character):
	"""
	Each night, choose a player (not yourself or Travellers): 
	you learn 1 good & 1 evil character, 1 of which is correct.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	@dataclass
	class Ping(info.Info):
		player: PlayerID
		character1: type[Character]
		character2: type[Character]

		def __call__(self, state: State, src: PlayerID) -> STBool:
			return (
				info.IsCharacter(self.player, self.character1)(state, src) |
				info.IsCharacter(self.player, self.character2)(state, src)
			)

@dataclass
class Drunk(Character):
	"""
	You do not know you are the Drunk. 
	You think you are a Townsfolk character, but you are not.
	"""
	category: ClassVar[Categories] = OUTSIDER
	is_liar: ClassVar[bool] = True
	# wake_pattern is decided during run_setup

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		drunk = state.players[me]
		self.wake_pattern = drunk.claim.wake_pattern
		"""Drunk can only 'lie' about being Townsfolk"""
		if drunk.claim.category is TOWNSFOLK:
			yield state

@dataclass
class Empath(Character):
	"""
	Each night, you learn how many of your 2 alive neighbors are evil.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	@dataclass
	class Ping(info.Info):
		count: int
		def __call__(self, state: State, src: PlayerID) -> STBool:
			left, right = (info.get_next_player_who_is(
				state,
				lambda s, p: info.IsAlive(p)(s, src) is info.TRUE,
				src,
				clockwise,
			) for clockwise in (True, False))
			evil_neighbours = [info.IsEvil(left)]
			if left != right:
				evil_neighbours.append(info.IsEvil(right))
			return info.ExactlyN(N=self.count, args=evil_neighbours)(state, src)

@dataclass
class FangGu(Character):
	category: ClassVar[Categories] = DEMON
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_STAR

	@staticmethod
	def modify_category_counts(bounds: CategoryBounds) -> CategoryBounds:
		(min_tf, max_tf), (min_out, max_out), mn, dm = bounds
		bounds = (min_tf - 1, max_tf - 1), (min_out + 1, max_out + 1), mn, dm
		return bounds

@dataclass
class FortuneTeller(Character):
	"""
	Each night, choose 2 players: you learn if either is a Demon. 
	There is a good player that registers as a Demon to you.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		demon: bool

		def __call__(self, state: State, me: PlayerID) -> STBool:
			real_result = (
				info.IsCategory(self.player2, DEMON)(state, me) |
				info.IsCategory(self.player1, DEMON)(state, me) |
				info.CharAttrEq(me, 'red_herring', self.player1)(state, me) |
				info.CharAttrEq(me, 'red_herring', self.player2)(state, me)
			)
			return real_result == info.STBool(self.demon)

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		# Any good player could be chosen as the red herring
		for player in range(len(state.players)):
			if info.IsEvil(player)(state, me) is not info.TRUE:
				new_state = state.fork()
				new_state.players[me].character.red_herring = player
				yield new_state

	def _world_str(self, state: State) -> str:
		"""For printing nice output representations of worlds"""
		return (
			f'{type(self).__name__} (Red Herring = '
			f'{state.players[self.red_herring].name})'
		)

@dataclass
class GenericDemon(Character):
	"""
	Many demons just kill once each night*, so implment that once here.
	"""
	category: ClassVar[Categories] = DEMON
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_STAR

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		"""Override Reason: Create a world for every kill choice."""
		demon = state.players[me]
		if night == 1 or demon.is_dead or demon.droison_count:
			yield state; return
		for target in range(len(state.players)):
			new_state = state.fork()
			target_char = new_state.players[target].character
			yield from target_char.attacked_at_night(new_state, target, me)

@dataclass
class Goblin(Character):
	"""TODO: Not yet implemented"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

@dataclass
class Imp(GenericDemon):
	"""
	Each night*, choose a player: they die. 
	If you kill yourself this way, a Minion becomes the Imp.
	"""

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		"""Override Reason: Add star pass to generic demon"""
		demon = state.players[me]
		if night == 1 or demon.is_dead or demon.droison_count:
			yield state; return
		for target in range(len(state.players)):
			if target == me:
				import sys  # TMP
				if 'unittest' not in sys.modules:
					pass  # print("Star pass not implemented yet")
			new_state = state.fork()
			target_char = new_state.players[target].character
			yield from target_char.attacked_at_night(new_state, target, me)

@dataclass
class Investigator(Character):
	"""
	You start knowing that 1 of 2 players is a particular Minion.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		character: type[Character]

		def __call__(self, state: State, src: PlayerID) -> STBool:
			return (
				info.IsCharacter(self.player1, self.character)(state, src) |
				info.IsCharacter(self.player2, self.character)(state, src)
			)

@dataclass
class Juggler(Character):
	"""
	On your 1st day, publicly guess up to 5 players' characters. 
	That night, you learn how many you got correct.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.MANUAL

	@dataclass
	class Juggle(events.Event):
		juggle: dict[PlayerID, Character]
		def __call__(self, state: State) -> StateGen:
			pass

	@dataclass
	class Ping(info.Info):
		count: int
		def __call__(self, state: State, me: PlayerID) -> STBool:
			juggler = state.players[me]
			juggle = getattr(juggler, 'juggle', None)
			assert state.night == juggler.character.first_night + 1, (
				"Juggler.Ping only allowed on Juggler's second night"
			)
			assert juggle is not None, (
				"No Juggler.Juggle happened before the Juggler.Ping")
			juggler.woke()
			return info.ExactlyN(
				N=self.count, 
				args=(
					info.IsCharacter(player, character)
					for player, character in juggle.items()
				)
			)(state, me)

	def run_day(self, state: State, day: int, me: PlayerID) -> StateGen:
		"""
		Overridden because: No vortox inversion, and the Juggler can make their
		guess even if droisoned or dead during the day.
		TODO!: juggle should be evaluated here during the day, not the night!
		"""
		juggler = state.players[me]
		if state.day in juggler.day_info:
			juggler.juggle = juggler.day_info[state.day].juggle
		yield state

@dataclass
class Knight(Character):
	"""
	You start knowing 2 players that are not the Demon.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID

		def __call__(self, state: State, src: PlayerID) -> STBool:
			return ~(
				info.IsCategory(self.player1, DEMON)(state, src) |
				info.IsCategory(self.player2, DEMON)(state, src)
			)

@dataclass
class Leviathan(Character):
	"""
	If more than 1 good player is executed, evil wins.
	All players know you are in play. After day 5, evil wins.
	"""
	category: ClassVar[Categories] = DEMON
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		"""Game ends if S&H Leviathan reaches Night 6."""
		leviathan = state.players[me]
		if (
			night < 6
			or leviathan.droison_count 
			or leviathan.is_dead
		):
			yield state



@dataclass
class Librarian(Character):
	"""
	You start knowing that 1 of 2 players is a particular Outsider. 
	(Or that zero are in play.)
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID | None
		player2: PlayerID | None = None
		character: type[Character] | None = None

		def __call__(self, state: State, src: PlayerID) -> STBool:
			usage = (
				'Librarian.Ping usage: '
				'Librarian.Ping(player1, player2, character) or Ping(None)'
			)
			if self.player1 is None:
				assert self.player2 is None and self.character is None, usage
				return info.ExactlyN(N=0, args=[
					info.IsCategory(player, OUTSIDER)
					for player in range(len(state.players))
				])(state, src)

			else:
				assert (self.player2 is not None 
					and self.character is not None), usage
				return (
					info.IsCharacter(self.player1, self.character)(state, src) |
					info.IsCharacter(self.player2, self.character)(state, src)
				)

@dataclass
class LordOfTyphon(GenericDemon):
	"""
	Each night*, choose a player: they die.[Evil characters are in a line. 
	You are in the middle. +1 Minion. -? to +? Outsiders]
	"""
	@staticmethod
	def modify_category_counts(bounds: CategoryBounds) -> CategoryBounds:
		(tf_lo, tf_hi), (out_lo, out_hi), (min_lo, min_hi), dm = bounds
		return (
			(tf_lo - 99, tf_hi),
			(out_lo - 99, out_hi + 99),
			(min_lo + 1, min_hi + 1),
			dm
		)

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		"""Override Reason: Check evil in a row, Typhon in middle."""
		evil = [player.is_evil for player in state.players]
		N = len(state.players)
		if not evil[(me - 1) % N] or not evil[(me + 1) % N]:
			return
		if 'e' * sum(evil) in ''.join('e' if e else 'g' for e in evil) * 2:
			yield state

@dataclass
class Lunatic(Character):
	"""
	You think you are the Demon, but you are not.
	The demon knows who you are & who you chose at night.
	"""
	category: ClassVar[Categories] = OUTSIDER
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_STAR

@dataclass
class Marionette(Character):
	"""
	You think you are a good character, but you are not. 
	The Demon knows who you are. [You neighbor the Demon]
	"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	# wake_pattern is decided during run_setup

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		"""Override Reason: Check neighbouring Demon"""
		self.wake_pattern = state.players[me].claim.wake_pattern
		N = len(state.players)
		demon_neighbour = (
			info.IsCategory((me - 1) % N, DEMON)(state, me) 
			| info.IsCategory((me + 1) % N, DEMON)(state, me)
		)
		if demon_neighbour is not info.FALSE:
			yield state

@dataclass
class Mayor(Character):
	"""
	If only 3 player live & no execution occurs, your team wins. 
	If you die at night, another player might die instead.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

@dataclass
class Mutant(Character):
	"""
	If you are "mad" about being an Outsider, you might be executed.
	"""
	category: ClassVar[Categories] = OUTSIDER
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	def run_night(self, state: State, night: int, src: PlayerID) -> StateGen:
		# Mutants never break madness in these puzzles
		player = state.players[src]
		if (
			player.droison_count 
			or player.is_dead
			or player.claim.category is not OUTSIDER
		):
			yield state

@dataclass
class Noble(Character):
	"""
	You start knowing 3 players, 1 and only 1 of which is evil.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		player3: PlayerID

		def __call__(self, state: State, src: PlayerID) -> STBool:
			return info.ExactlyN(N=1, args=(
				info.IsEvil(self.player1),
				info.IsEvil(self.player2),
				info.IsEvil(self.player3),
			))(state, src)

@dataclass
class NoDashii(GenericDemon):
	"""
	Each night*, choose a player: they die. 
	Your 2 Townsfolk neighbors are poisoned.
	"""
	tf_neighbour1: PlayerID | None = None
	tf_neighbour2: PlayerID | None = None

	def run_setup(self, state: State, src: PlayerID) -> StateGen:
		# I allow the No Dashii to poison misregistering characters (e.g. Spy),
		# so there may be multiple possible combinations of neighbour pairs
		# depending on ST choices. Find them all and create a world for each.
		N = len(state.players)
		fwd_candidates, bkwd_candidates = [], []
		for candidates, direction in (
			(fwd_candidates, 1),
			(bkwd_candidates, -1),
		):
			for step in range(1, N):
				player = (src + direction * step) % N
				is_tf = info.IsCategory(player, TOWNSFOLK)(state, src)
				if is_tf is not info.FALSE:
					candidates.append(player)
				if is_tf is info.TRUE:
					break
		# Create a world or each combination of left and right poisoned player
		for fwd in fwd_candidates:
			for bkwd in bkwd_candidates:
				new_state = state.fork()
				new_nodashii = new_state.players[src].character
				new_nodashii.tf_neighbour1 = fwd
				new_nodashii.tf_neighbour2 = bkwd
				new_nodashii.maybe_activate_effects(new_state, src)
				yield new_state

	def _activate_effects_impl(self, state: State, src: PlayerID):
		state.players[self.tf_neighbour1].droison(state, src)
		state.players[self.tf_neighbour2].droison(state, src)

	def _deactivate_effects_impl(self, state: State, src: PlayerID):
		state.players[self.tf_neighbour1].undroison(state, src)
		state.players[self.tf_neighbour2].undroison(state, src)

	def _world_str(self, state):
		return 'NoDashii (Poisoned {} & {})'.format(
			state.players[self.tf_neighbour1].name,
			state.players[self.tf_neighbour2].name,
		)

@dataclass
class Oracle(Character):
	"""
	Each night*, you learn how many dead players are evil.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_STAR

	@dataclass
	class Ping(info.Info):
		count: int
		def __call__(self, state: State, src: PlayerID) -> STBool:
			return info.ExactlyN(
				N=self.count, 
				args=[
					info.IsEvil(player) & ~info.IsAlive(player)
					for player in range(len(state.players))
				]
			)(state, src)

@dataclass
class Poisoner(Character):
	"""
	Each night, choose a player: they are poisoned tonight and tomorrow day.
	"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	target: PlayerID = None

	# Keep history just for debug and pretty printing the history of a game.
	target_history: list[PlayerID] = field(default_factory=list)

	def run_night(self, state: State, night: int, src: PlayerID) -> StateGen:
		"""Override Reason: Create a world for every poisoning choice."""
		poisoner = state.players[src]
		if poisoner.is_dead:
			yield state; return
		for target in range(len(state.players)):
			new_state = state.fork()
			new_poisoner = new_state.players[src].character
			# Even droisoned poisoners make a choice, because they might be 
			# undroisoned before dusk.
			new_poisoner.target = target
			new_poisoner.target_history.append(target)
			new_poisoner.maybe_activate_effects(new_state, src)
			yield new_state

	def end_day(self, state: State, day: int, me: PlayerID) -> bool:
		self.maybe_deactivate_effects(state, me)
		self.target = None
		return True

	def _activate_effects_impl(self, state: State, me: PlayerID):
		if self.target == me:
			state.players[me].droison_count += 1
		elif self.target is not None:
			state.players[self.target].droison(state, me)

	def _deactivate_effects_impl(self, state: State, me: PlayerID):
		if self.target == me:
			state.players[me].droison_count -= 1
		elif self.target is not None:
			state.players[self.target].undroison(state, me)

	def _world_str(self, state: State) -> str:
		return (
			f'{type(self).__name__} (Poisoned '
			f'{", ".join(state.players[p].name for p in self.target_history)})'
		)


@dataclass
class Pukka(Character):
	"""
	Each night, choose a player: they are poisoned.
	The previously poisoned player dies then becomes healthy.
	"""
	category: ClassVar[Categories] = DEMON
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	target: PlayerID | None = None

	# For pretty printing the history of a game.
	target_history: list[PlayerID] = field(default_factory=list)

	def run_night(self, state: State, day: int, me: PlayerID) -> StateGen:
		"""TODO: This wouldn't handle picking a Goon"""
		pukka = state.players[me]
		if pukka.is_dead or pukka.droison_count:
			yield state
			return

		# A Pukka's new target is poisoned, then the previous target dies, and
		# _then_ the previous target becomes sober. For that reason we can't use
		# `maybe_deactivate_effects` because target will have changed, so we
		# manually handle the unpoisoning of the killed player.
		self.effects_active = False
		for new_target in range(len(state.players)):
			new_state = state.fork()
			new_pukka = new_state.players[me].character
			new_pukka.target = new_target
			new_pukka.target_history.append(new_target)
			new_pukka.maybe_activate_effects(new_state, me)
			if self.target is None:
				yield new_state
			else:
				target_char = new_state.players[self.target].character
				for substate in target_char.attacked_at_night(
					new_state, self.target, me
				):
					substate.players[self.target].undroison(substate, me)
					yield substate



	def end_day(self, state: State, day: int, me: PlayerID) -> bool:
		self.maybe_deactivate_effects(state, me)
		return True

	def _activate_effects_impl(self, state: State, me: PlayerID):
		state.players[self.target].droison(state, me)

	def _deactivate_effects_impl(self, state: State, me: PlayerID):
		# Break a self-poisoning infinite recursion, whilst still leaving the 
		# Pukka marked as droisoned.
		if self.target != me:
			state.players[self.target].undroison(state, me)

@dataclass
class Ravenkeeper(Character):
	"""
	If you die at night, you are woken to choose a player:
	you learn their character.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.MANUAL

	death_night: int | None = None

	@dataclass
	class Ping(info.Info):
		player: PlayerID
		character: type[Character]

		def __call__(self, state: State, src: PlayerID) -> STBool:
			assert state.night > 1, "Ravenkeepers don't die night 1!"
			ravenkeeper = state.players[src].character
			death_night = ravenkeeper.death_night
			if death_night is None or death_night != state.night:
				return info.FALSE
			return info.IsCharacter(self.player, self.character)(state, src)

	def killed(self, state: State, me: PlayerID) -> StateGen:
		"""Override Reason: Record when death happened."""
		if state.night is not None:
			self.death_night = state.night
			state.players[me].woke()
		yield from super().killed(state, me)

	def run_night(self, state: State, night: int, me: PlayerID) -> StateGen:
		"""
		Override Reason: Even if dead.
		The Ping checks the death was on the same night.
		"""
		if self.default_info_check(
			state, state.players[me].night_info, night, me, even_if_dead=True
		):
			yield state

@dataclass
class Recluse(Character):
	"""
	You might register as evil & as a Minion or Demon, even if dead.
	"""
	category: ClassVar[Categories] = OUTSIDER
	is_liar: ClassVar[bool] = False
	misregister_categories: ClassVar[tuple[Categories, ...]] = (MINION, DEMON)
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER


@dataclass
class Savant(Character):
	"""
	Each day, you may visit the Storyteller to learn 2 things in private: 
	one is true & one is false.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	@dataclass
	class Ping(info.Info):
		a: info.Info
		b: info.Info
		def __call__(self, state: State, src: PlayerID):
			a, b = self.a(state, src), self.b(state, src)
			if state.vortox:
				return not (a | b)
			return a ^ b

	def run_day(self, state: State, day: int, me: PlayerID) -> StateGen:
		""" Override Reason: Novel Vortox effect on Savant, see Savant.Ping."""
		savant = state.players[me]
		if (
			savant.is_dead
			or savant.is_evil
			or savant.droison_count
			or day not in savant.day_info
		):
			yield state; return
		ping = savant.day_info[day]
		result = ping(state, me)
		if result is not info.FALSE:
			yield state

@dataclass
class ScarletWoman(Character):
	"""
	If there are 5 or more players alive & the Demon dies, you become the Demon.
	(Travellers don't count).
	"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.MANUAL

	def death_in_town(self, state: State, death: PlayerID, me: PlayerID):
		"""Catch a Demon death. I don't allow catching Recluse deaths."""
		scarletwoman = state.players[me]
		dead_player = state.players[death]
		living_players = sum(not p.is_dead for p in state.players)
		if (
			not scarletwoman.is_dead
			and scarletwoman.droison_count == 0
			and dead_player.character.category is DEMON
			and living_players >= 4
		):
			if state.night is not None:
				scarletwoman.woke()
			state.character_change(me, type(dead_player.character))

@dataclass
class Seamstress(Character):
	"""
	Once per game, at night, choose 2 players (not yourself):
	you learn if they are the same alignment.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		same: bool
		def __call__(self, state: State, src: PlayerID) -> STBool:
			a = info.IsEvil(self.player1)(state, src)
			b = info.IsEvil(self.player2)(state, src)
			enemies = a ^ b
			if self.same:
				return ~enemies
			return enemies

@dataclass
class Shugenja(Character):
	"""
	You start knowing if your closest evil player is clockwise or 
	anti-clockwise. If equidistant, this info is arbitrary.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		clockwise: bool
		def __call__(self, state: State, src: PlayerID) -> STBool:
			N = len(state.players)
			direction = 1 if self.clockwise else - 1
			evils = [None] + [
				info.IsEvil((src + direction * step) % N)(state, src)
				for step in range(1, N)
			]
			fwd_maybe, bwd_maybe, fwd_true, bwd_true = N, N, N, N
			for step in range(N // 2, 0, -1):
				if evils[step] is info.TRUE:
					fwd_true, fwd_maybe = step, step
				elif evils[step] is info.MAYBE:
					fwd_maybe = step
				if evils[-step] is info.TRUE:
					bwd_true, bwd_maybe = step, step
				elif evils[-step] is info.MAYBE:
					bwd_maybe = step

			if bwd_true < fwd_maybe:
				return info.FALSE
			if fwd_true < bwd_maybe:
				return info.TRUE
			return info.MAYBE
		
		
@dataclass
class Soldier(Character):
	"""
	You are safe from the Demon.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		"""Override Reason: Activate safe_from_demon."""
		self.maybe_activate_effects(state, me)
		yield state

	def _activate_effects_impl(self, state: State, me: PlayerID) -> None:
		soldier = state.players[me]
		# Characetrs like monk might delete the attr if it hits 0, so recreate
		# it if neccessary.
		if hasattr(soldier, 'safe_from_demon_count'):
			soldier.safe_from_demon_count += 1
		else:
			soldier.safe_from_demon_count = 1

	def _deactivate_effects_impl(self, state: State, me: PlayerID) -> None:
		state.players[me].safe_from_demon_count -= 1


@dataclass
class Steward(Character):
	"""
	You start knowing 1 good player.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player: PlayerID
		def __call__(self, state: State, src: PlayerID) -> STBool:
			return ~info.IsEvil(self.player)(state, src)

@dataclass
class Saint(Character):
	"""
	If you die by execution, your team loses.
	"""
	category: ClassVar[Categories] = OUTSIDER
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	def executed(self, state: State, me: PlayerID, died: bool) -> StateGen:
		"""
		Override Reason: Game is not over, execution is not a valid world.
		We let the super method handle any non-Saint-related execution details.
		"""
		if state.players[me].droison_count or not died:
			yield from super().executed(self, state, me, died)


@dataclass
class Slayer(Character):
	"""
	Once per game, during the day, publicly choose a player: 
	if they are the Demon, they die.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.NEVER

	spent: bool = False

	@dataclass
	class Shot(events.Event):
		src: PlayerID
		target: PlayerID
		died: bool

		def __call__(self, state: State) -> StateGen:
			shooter = state.players[self.src]
			target = state.players[self.target]
			if (
				shooter.is_dead
				or target.is_dead
				or not isinstance(shooter.character, Slayer)
				or shooter.droison_count
				or shooter.character.spent
			):
				should_die = info.FALSE
			else:
				should_die = info.IsCategory(self.target, DEMON)(
					state, self.src
				)

			if isinstance(shooter.character, Slayer):
				shooter.character.spent = True

			if self.died and should_die is not info.FALSE:
				yield from target.character.killed(state, self.target)
			elif not self.died and should_die is not info.TRUE:
				yield state

@dataclass
class Spy(Character):
	"""
	Each night, you see the Grimoire. You might register as good & as a 
	Townsfolk or Outsider, even if dead.
	"""
	category: ClassVar[Categories] = MINION
	is_liar: ClassVar[bool] = True
	misregister_categories: ClassVar[tuple[Categories, ...]] = (
		TOWNSFOLK, OUTSIDER
	)
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

@dataclass
class Undertaker(Character):
	"""
	Each night*, you learn which character died by execution today.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT_STAR

	@dataclass
	class Ping(info.Info):
		player: PlayerID | None
		character: type[Character] | None

		def __call__(self, state: State, src: PlayerID) -> STBool:
			assert state.night > 1, "Undertaker acts from second night."
			assert (self.character is None) == (self.player is None)

			previous_day_events = state.day_events.get(state.night - 1, [])
			if self.player is None:
				return STBool(
					not any(
						isinstance(e, events.Execution) and e.died 
						for e in previous_day_events
					)
				)
			elif any(
				isinstance(event, events.Execution)
				and event.player == self.player
				and event.died
				for event in previous_day_events
			):
				return info.IsCharacter(self.player, self.character)(state, src)
			return info.FALSE

@dataclass
class WasherWoman(Character):
	"""
	You start knowing that 1 of 2 players is a particular Townsfolk.
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.FIRST_NIGHT

	@dataclass
	class Ping(info.Info):
		player1: PlayerID
		player2: PlayerID
		character: Character
		def __call__(self, state: State, src: PlayerID) -> STBool:
			return (
				info.IsCharacter(self.player1, self.character)(state, src) |
				info.IsCharacter(self.player2, self.character)(state, src)
			)


@dataclass
class VillageIdiot(Character):
	"""
	Each night, choose a player: you learn their alignment. 
	[+0 to +2 Village Idiots. 1 of the extras is drunk]
	"""
	category: ClassVar[Categories] = TOWNSFOLK
	is_liar: ClassVar[bool] = False
	wake_pattern: ClassVar[WakePattern] = WakePattern.EACH_NIGHT

	is_drunk_VI: bool = False

	@dataclass
	class Ping(info.Info):
		player: PlayerID
		is_evil: bool
		def __call__(self, state: State, src: PlayerID) -> STBool:
			registers_evil = info.IsEvil(self.player)(state, src)
			return registers_evil == info.STBool(self.is_evil)

	def run_setup(self, state: State, src: PlayerID) -> StateGen:
		# If there is more than one Village Idiot, choose one to be the drunk VI
		VIs = [i for i, player in enumerate(state.players)
				if isinstance(player.character, VillageIdiot)]
		already_done = any(state.players[p].character.is_drunk_VI for p in VIs)
		if len(VIs) == 1 or already_done:
			yield state
			return

		for vi in VIs:
			new_state = state.fork()
			new_state.players[vi].droison_count += 1
			new_state.players[vi].character.is_drunk_VI = True
			yield new_state

	def _world_str(self, state: State) -> str:
		"""For printing nice output representations of worlds"""
		ret = type(self).__name__
		if self.is_drunk_VI:
			ret += ' (Drunk)'
		return ret


@dataclass
class Vortox(GenericDemon):
	"""
	Each night*, choose a player: they die. 
	Townsfolk abilities yield false info.
	Each day, if no-one was executed, evil wins.
	"""

	def run_setup(self, state: State, me: PlayerID) -> StateGen:
		"""Override Reason: Vortox immediately activates effects."""
		self.maybe_activate_effects(state, me)
		yield state

	def end_day(self, state: State, day: int, me: PlayerID) -> bool:
		events_ = state.day_events.get(day, [])
		return any(isinstance(ev, events.Execution) for ev in events_)

	def _activate_effects_impl(self, state: State, me: PlayerID) -> None:
		state.vortox = True

	def _deactivate_effects_impl(self, state: State, me: PlayerID) -> None:
		state.vortox = False


@dataclass
class Zombuul(Character):
	"""Not implemented properly yet"""
	category: ClassVar[Categories] = DEMON
	is_liar: ClassVar[bool] = True
	wake_pattern: ClassVar[WakePattern] = WakePattern.MANUAL

	registering_dead: bool = False



GLOBAL_SETUP_ORDER = [
	Vortox,
	Marionette,
	NoDashii,
	FortuneTeller,
	VillageIdiot,
	Drunk,
	Soldier,
	LordOfTyphon,  # Goes last so that evils created in setup must be in a line
]

GLOBAL_NIGHT_ORDER = [
	Leviathan,
	Courtier,
	Poisoner,
	ScarletWoman,
	Imp,
	Pukka,
	FangGu,
	NoDashii,
	Vortox,
	LordOfTyphon,
	Ravenkeeper,
	WasherWoman,
	Librarian,
	Investigator,
	Chef,
	Empath,
	FortuneTeller,
	Undertaker,
	Clockmaker,
	Dreamer,
	Oracle,
	Seamstress,
	Juggler,
	Steward,
	Knight,
	Noble,
	Balloonist,
	Shugenja,
	VillageIdiot,
	Chambermaid,
]

GLOBAL_DAY_ORDER = [
	Alsaahir,
	Juggler,
	Savant,
	Slayer,
	Saint,
	Mutant,
]

INACTIVE_CHARACTERS = [
	Baron,
	Drunk,
	Goblin,
	Lunatic,
	Marionette,
	Mayor,
	Recluse,
	Soldier,
	Spy,
]
