import unittest

from worldcup_simulator import (
    R32_SLOTS,
    THIRD_PLACE_ASSIGNMENTS,
    THIRD_PLACE_WINNER_SLOT_ORDER,
    resolve_slot,
    third_place_assignment_for_groups,
)


class ThirdPlaceAssignmentsTest(unittest.TestCase):
    def test_all_495_combinations_are_available(self):
        self.assertEqual(len(THIRD_PLACE_ASSIGNMENTS), 495)
        for key, assignment in THIRD_PLACE_ASSIGNMENTS.items():
            self.assertEqual(set(assignment), set(THIRD_PLACE_WINNER_SLOT_ORDER))
            self.assertEqual(sorted(slot[1] for slot in assignment.values()), sorted(key))

    def test_full_a_to_h_combination_matches_official_table_order(self):
        assignment = third_place_assignment_for_groups(set("ABCDEFGH"))
        self.assertEqual(
            assignment,
            {
                "1A": "3H",
                "1B": "3G",
                "1D": "3B",
                "1E": "3C",
                "1G": "3A",
                "1I": "3F",
                "1K": "3D",
                "1L": "3E",
            },
        )

    def test_assignments_fit_their_round_of_32_slot_constraints(self):
        allowed_by_winner = {
            left: set(right[1:].split("/"))
            for left, right in R32_SLOTS
            if right.startswith("3")
        }
        self.assertEqual(set(allowed_by_winner), set(THIRD_PLACE_WINNER_SLOT_ORDER))

        for assignment in THIRD_PLACE_ASSIGNMENTS.values():
            for winner_slot, third_slot in assignment.items():
                self.assertIn(third_slot[1], allowed_by_winner[winner_slot])

    def test_resolve_slot_uses_assignment_instead_of_greedy_order(self):
        positions = {"1E": "Winner E"}
        thirds = {"A": "Third A", "B": "Third B", "C": "Third C", "D": "Third D"}
        assignment = {"1E": "3C"}

        self.assertEqual(
            resolve_slot("3A/B/C/D/F", positions, thirds, assignment, "1E"),
            "Third C",
        )

    def test_resolve_slot_rejects_invalid_assignment_for_match(self):
        positions = {"1E": "Winner E"}
        thirds = {"H": "Third H"}
        assignment = {"1E": "3H"}

        with self.assertRaises(ValueError):
            resolve_slot("3A/B/C/D/F", positions, thirds, assignment, "1E")


if __name__ == "__main__":
    unittest.main()
