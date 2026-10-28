"""Encouragement uses sourced quotations occasionally, without blocking speech."""
import unittest

import motivational_quotes as quotes


class MotivationalQuotesTest(unittest.TestCase):
    def test_curated_quotes_have_authors_sources_and_explicit_meaning_translations(self):
        authors = {q['author'] for q in quotes.QUOTES}
        self.assertEqual(authors, {'Benjamin Franklin', 'Thomas Edison', 'Helen Keller', 'Nelson Mandela'})
        for item in quotes.QUOTES:
            self.assertTrue(item['source_url'].startswith('https://'))
            self.assertTrue(item['english'] and item['meaning_vi'])
        context = quotes.prompt_context()
        self.assertIn('meaning translation', context)
        self.assertIn('Never invent', context)
        self.assertIn('English-only', context)

    def test_first_three_invitations_and_all_hints_do_not_add_a_quote(self):
        stats = {}
        for index in range(3):
            self.assertEqual(quotes.invitation_hint(stats, index, False, 1000), '')
        self.assertEqual(quotes.invitation_hint(stats, 3, True, 1000), '')
        self.assertEqual(stats, {})

    def test_quotes_are_spaced_and_rotate_after_cooldown(self):
        stats = {}
        first = quotes.invitation_hint(stats, 3, False, 1000)
        self.assertIn('Benjamin Franklin', first)
        self.assertEqual(quotes.invitation_hint(stats, 7, False, 1001), '')
        second = quotes.invitation_hint(stats, 11, False, 1601)
        self.assertIn('Thomas Edison', second)
        self.assertNotEqual(first, second)

    def test_quote_history_is_private_to_each_robot_session(self):
        first, second = {}, {}
        quotes.invitation_hint(first, 3, False, 1000)
        self.assertIn('Benjamin Franklin', quotes.invitation_hint(second, 3, False, 1001))


if __name__ == '__main__':
    unittest.main()
