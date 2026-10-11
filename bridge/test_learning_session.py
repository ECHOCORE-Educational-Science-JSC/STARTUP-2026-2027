import unittest

import learning_session


class VocabularyPrefetchTest(unittest.TestCase):
    def requests(self, text):
        return learning_session.vocabulary_prefetch_requests(text)

    def test_explicit_english_list_preserves_order_and_item_attributes(self):
        self.assertEqual(self.requests("Teach me red apple, yellow banana and orange cat in cartoon style"), [
            {"word": "apple", "query": "red apple cartoon"},
            {"word": "banana", "query": "yellow banana cartoon"},
            {"word": "cat", "query": "orange cat cartoon"},
        ])

    def test_vietnamese_list_translates_each_subject_and_its_color(self):
        self.assertEqual(self.requests("Dạy các từ con mèo màu cam, con voi màu trắng và con tôm hùm dạng hoạt hình"), [
            {"word": "cat", "query": "orange cat cartoon"},
            {"word": "elephant", "query": "white elephant cartoon"},
            {"word": "lobster", "query": "lobster cartoon"},
        ])

    def test_vietnamese_dishes_keep_whole_names(self):
        self.assertEqual(self.requests("Kể các món bún bò Huế, phở bò và bánh mì"), [
            {"word": "bun bo hue", "query": "bun bo hue"},
            {"word": "pho bo", "query": "pho bo"},
            {"word": "banh mi", "query": "banh mi"},
        ])

    def test_accented_vietnamese_list_disambiguates_bare_nouns(self):
        self.assertEqual(self.requests("Dạy các từ táo, chuối, bơ, dừa và nấm"), [
            {"word": "apple", "query": "apple"},
            {"word": "banana", "query": "banana"},
            {"word": "avocado", "query": "avocado"},
            {"word": "coconut", "query": "coconut"},
            {"word": "mushroom", "query": "mushroom"},
        ])

    def test_bare_known_english_list_is_a_prefetch_request(self):
        self.assertEqual(self.requests("apple, banana and orange"), [
            {"word": "apple", "query": "apple"},
            {"word": "banana", "query": "banana"},
            {"word": "orange", "query": "orange"},
        ])

    def test_item_counts_are_preserved_without_using_overall_list_count(self):
        self.assertEqual(self.requests("Teach two black cats and three white dogs as photos"), [
            {"word": "cat", "query": "two black cat photo"},
            {"word": "dog", "query": "three white dog photo"},
        ])

    def test_scene_items_preserve_actions_settings_counts_and_style(self):
        self.assertEqual(self.requests("Teach vocabulary: two black cats sitting on a sofa, one dog running in a park, photo"), [
            {"word": "cat", "query": "two black cat sitting on a sofa photo"},
            {"word": "dog", "query": "one dog running in a park photo"},
        ])

    def test_vietnamese_scene_items_preserve_their_actions(self):
        self.assertEqual(self.requests("Dạy các từ hai con mèo màu cam đang ngủ và ba con chó màu trắng đang chạy dạng hoạt hình"), [
            {"word": "cat", "query": "two orange cat sleeping cartoon"},
            {"word": "dog", "query": "three white dog running cartoon"},
        ])

    def test_vietnamese_bare_color_adjectives_are_preserved(self):
        self.assertEqual(self.requests("Dạy con mèo vàng và con chó đen"), [
            {"word": "cat", "query": "yellow cat"},
            {"word": "dog", "query": "black dog"},
        ])

    def test_unpunctuated_vietnamese_colors_bind_to_the_preceding_subject(self):
        text = "Dạy các từ con mèo màu cam con chó màu trắng"
        self.assertEqual(self.requests(text), [
            {"word": "cat", "query": "orange cat"},
            {"word": "dog", "query": "white dog"},
        ])
        state = learning_session.LearningVisualState()
        state.observe_user(text)
        self.assertEqual(state.authoritative_visual_request("dog", "white dog"),
                         ("dog", "white dog"))

    def test_sequential_vietnamese_subjects_keep_their_distinct_colors(self):
        for separator in ("rồi", "sau đó", "then"):
            with self.subTest(separator=separator):
                text = f"Dạy các từ con mèo đen {separator} con mèo trắng"
                self.assertEqual(self.requests(text), [
                    {"word": "cat", "query": "black cat"},
                    {"word": "cat", "query": "white cat"},
                ])
                state = learning_session.LearningVisualState()
                state.observe_user(text)
                self.assertEqual(state.authoritative_visual_request("cat", "white cat"),
                                 ("cat", "white cat"))

    def test_unknown_scene_attributes_keep_original_clause_for_verification(self):
        text = "Teach a tiny Bengal cat and a large husky dog as photos"
        requests = self.requests(text)
        self.assertEqual([item["word"] for item in requests], ["cat", "dog"])
        self.assertIn("tiny Bengal cat", requests[0]["query"])
        self.assertIn("large husky dog", requests[1]["query"])
        state = learning_session.LearningVisualState()
        state.observe_user(text)
        self.assertEqual(state.authoritative_visual_request("cat", "cat"),
                         ("cat", requests[0]["query"]))

    def test_unpunctuated_fruit_list_keeps_orange_as_a_subject(self):
        self.assertEqual(self.requests("Teach apple orange banana"), [
            {"word": "apple", "query": "apple"},
            {"word": "orange", "query": "orange"},
            {"word": "banana", "query": "banana"},
        ])

    def test_category_request_preserves_shared_color(self):
        self.assertEqual(self.requests("List two black animal words as photos"), [
            {"word": "cat", "query": "black cat photo"},
            {"word": "dog", "query": "black dog photo"},
        ])

    def test_requested_counts_generate_concrete_items_for_each_category(self):
        cases = [
            ("Tell me 20 English words about animals", 20, "cat"),
            ("Kể cho bé mười từ tiếng Anh về trái cây", 10, "apple"),
            ("List five vehicle words", 5, "car"),
            ("Dạy hai mươi từ vựng về đồ ăn", 20, "bread"),
            ("Kể 5 từ về các con vật", 5, "cat"),
        ]
        for text, count, first in cases:
            with self.subTest(text=text):
                requests = self.requests(text)
                self.assertEqual(len(requests), count)
                self.assertEqual(requests[0], {"word": first, "query": first})
                self.assertEqual(len({item["word"] for item in requests}), count)

    def test_large_category_request_is_bounded(self):
        self.assertEqual(len(self.requests("List 100 animal words")), 40)

    def test_not_a_vocabulary_list_does_not_prefetch(self):
        for text in (
            "Show me two orange cats", "Con voi sống ở đâu?",
            "Play Baby Shark and Five Little Ducks", "Mở nhạc con voi và con mèo",
            "Tăng âm lượng lên 20", "Kể chuyện về Nam, Hoa và Mai",
            "Tell me 20 words about grammar", "I like apples and bananas",
            "Tell me why cats and dogs fight", "Kể câu chuyện về con mèo và con chó",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.requests(text), [])

    def test_explicit_known_list_deduplicates_repeated_requests(self):
        self.assertEqual(self.requests("List cat, dog, cat and elephant"), [
            {"word": "cat", "query": "cat"},
            {"word": "dog", "query": "dog"},
            {"word": "elephant", "query": "elephant"},
        ])

    def test_state_drains_streamed_list_and_resets_at_turn_end(self):
        state = learning_session.LearningVisualState()
        drain = state.prefetch_requests
        state.observe_user("Dạy các từ con mèo,")
        self.assertEqual(drain(), [{"word": "cat", "query": "cat"}])
        state.observe_user("con chó và con voi")
        self.assertEqual(drain(), [
            {"word": "dog", "query": "dog"},
            {"word": "elephant", "query": "elephant"},
        ])
        self.assertEqual(drain(), [])
        state.finish_turn()
        state.observe_user("Dạy các từ con mèo và con chó")
        self.assertEqual(len(drain()), 2)


class LearningVisualStateTest(unittest.TestCase):
    def test_chicken_feet_dish_overrides_generic_animal_tool_subject(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Tôi muốn ăn chân gà sả tắc. Bạn có thể cho tôi xem hình được không?')
        word, query = state.authoritative_visual_request('chicken', 'chicken')
        self.assertEqual(word, 'chan ga sa tac')
        self.assertIn('chan ga sa tac', query)
        self.assertNotEqual(state.turn_word, 'chicken')
        self.assertNotIn('user scene:', query)
        self.assertNotIn('Bạn có thể', query)

    def test_food_query_strips_wake_name_and_fillers_without_losing_plate(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Wisio, ừ tôi muốn xem chân gà sả tắc trong đĩa trắng.')
        word, query = state.authoritative_visual_request('chicken', 'chicken photo')
        self.assertEqual(word, 'chan ga sa tac')
        self.assertIn('dia trang', query)
        self.assertNotIn('toi muon xem', query)
        self.assertNotIn('wisio', query)

    def test_named_dish_preserves_requested_serving_scene_and_style(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Tôi muốn xem chân gà sả tắc trong đĩa trắng dạng hoạt hình. Cho tôi xem hình nhé.')
        word, query = state.authoritative_visual_request('chicken', 'chicken')
        self.assertEqual(word, 'chan ga sa tac')
        self.assertIn('trong dia trang', query)
        self.assertIn('cartoon', query)
        self.assertNotIn('photo', query)

    def test_named_dish_keeps_plate_before_subject_and_in_a_later_sentence(self):
        for utterance in ('Cho xem ảnh một đĩa trắng đựng chân gà sả tắc.',
                          'Cho xem chân gà sả tắc. Đựng trong đĩa trắng, dạng hoạt hình.'):
            with self.subTest(utterance=utterance):
                state = learning_session.LearningVisualState()
                state.observe_user(utterance)
                word, query = state.authoritative_visual_request('chicken', 'chicken photo')
                self.assertIn('dia trang', query)
                self.assertFalse(query.startswith('one chan ga'))


    def test_teaching_about_a_single_dish_does_not_reduce_it_to_an_animal(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Kể cho tôi về chân gà sả tắc và cho tôi xem hình')
        word, query = state.authoritative_visual_request('chicken', 'chicken photo')
        self.assertEqual(word, 'chan ga sa tac')


    def test_failed_image_attempt_does_not_trigger_correction_or_direct_retry(self):
        state = learning_session.LearningVisualState()
        state.observe_user('Cho xem hình con mèo màu cam')
        word, query = state.authoritative_visual_request('cat', 'orange cat photo')
        state.mark_image_failure(word, query, 'GEMINI_VERIFY_HTTP_503')
        self.assertIsNone(state.correction_prompt())
        state.correction_sent = True
        self.assertIsNone(state.fallback_request())
        self.assertIn('HTTP_503', state.failed_image_error(word, query))
        state.finish_turn()
        self.assertIn('HTTP_503', state.failed_image_error(word, query))
        state.observe_user('Cho xem hình con mèo màu cam lần nữa')
        self.assertIsNone(state.failed_image_error(word, query))

    def test_authoritative_single_request_overrides_missing_scene_attributes(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Show two black cats sitting on a sofa as a photo")
        authoritative = state.authoritative_visual_request
        self.assertEqual(authoritative("cat", "cat"),
                         ("cat", "two black cat sitting on a sofa photo"))

    def test_authoritative_single_request_rejects_wrong_subject(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem con mèo màu cam đang ngủ")
        authoritative = state.authoritative_visual_request
        with self.assertRaises(learning_session.learning_image.LearningImageError):
            authoritative("dog", "orange dog sleeping")

    def test_unrelated_image_does_not_satisfy_single_requested_subject(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem con mèo")
        state.mark_image("dog")
        self.assertFalse(state.image_shown)
        self.assertIsNone(state.last_image_word)
        self.assertIsNotNone(state.correction_prompt())

    def test_authoritative_batch_items_reuse_their_exact_prefetch_queries(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Teach red apple and white cat as a cartoon")
        authoritative = state.authoritative_visual_request
        self.assertEqual(authoritative("cat", "cat photo"), ("cat", "white cat cartoon"))
        state.mark_image("cat")
        self.assertTrue(state.image_shown)

    def test_counted_category_allows_alternate_word_with_shared_attributes(self):
        state = learning_session.LearningVisualState()
        state.observe_user("List two black animal words as photos")
        authoritative = state.authoritative_visual_request
        self.assertEqual(authoritative("rabbit", "rabbit"), ("rabbit", "black rabbit photo"))

    def test_counted_category_rejects_known_subject_from_another_category(self):
        state = learning_session.LearningVisualState()
        state.observe_user("List five animal words")
        with self.assertRaises(learning_session.learning_image.LearningImageError):
            state.authoritative_visual_request("car", "car")

    def test_unknown_direct_subject_keeps_user_clause_for_verifier(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem nghêu hấp sả")
        word, query = state.authoritative_visual_request("seafood", "steamed seafood")
        self.assertEqual(word, "seafood")
        self.assertIn("Cho xem nghêu hấp sả", query)

    def test_category_size_attribute_reaches_prefetch_and_authoritative_query(self):
        state = learning_session.LearningVisualState()
        state.observe_user("List two tiny black animal words as photos")
        requests = state.prefetch_requests()
        self.assertIn("tiny", requests[0]["query"])
        self.assertEqual(state.authoritative_visual_request("cat", "cat"),
                         ("cat", requests[0]["query"]))

    def test_lesson_without_user_subject_keeps_assistant_selected_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Dạy tiếng Anh cho bé")
        state.observe_assistant("This is an elephant")
        state.mark_image("elephant")
        self.assertTrue(state.image_shown)

    def test_vietnamese_dish_keeps_full_subject_for_proactive_visual(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Bún bò Huế là món gì vậy?")
        self.assertEqual(state.turn_word, "bun bo hue")
        self.assertIsNotNone(state.correction_prompt())
        self.assertEqual(state.fallback_request(), ("bun bo hue", "bun bo hue"))

    def test_vietnamese_lesson_request_requires_visual_for_concrete_word(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Dạy tiếng Anh cho bé đi")
        state.observe_assistant("Apple nghĩa là quả táo. Bé đọc theo Wisio nhé!")
        prompt = state.correction_prompt()
        self.assertIn("show_learning_image", prompt)
        self.assertIn("apple", prompt.casefold())
        self.assertIsNone(state.correction_prompt())

    def test_abstract_grammar_turn_does_not_require_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Mình luyện tiếng Anh nhé")
        state.observe_assistant("Hôm nay mình luyện thì hiện tại đơn và cách đặt câu hỏi.")
        self.assertIsNone(state.correction_prompt())

    def test_successful_image_satisfies_turn_and_avoids_immediate_repeat(self):
        state = learning_session.LearningVisualState()
        state.observe_user("learn English")
        state.observe_assistant("This is an elephant.")
        state.mark_image("elephant")
        self.assertIsNone(state.correction_prompt())
        state.finish_turn()
        state.observe_assistant("Elephant means con voi.")
        self.assertIsNone(state.correction_prompt())

    def test_stop_phrase_leaves_lesson_mode(self):
        state = learning_session.LearningVisualState()
        state.observe_user("dạy tiếng Anh")
        self.assertTrue(state.active)
        state.observe_user("thôi học tiếng Anh, đổi chủ đề")
        self.assertFalse(state.active)
        state.observe_assistant("Apple")
        self.assertIsNone(state.correction_prompt())

    def test_vietnamese_concrete_request_supplies_english_word(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Dạy tiếng Anh con voi")
        self.assertEqual(state.turn_word, "elephant")

    def test_concrete_topic_in_normal_conversation_proactively_requires_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Con tôm hốp sống ở đâu vậy?")
        self.assertEqual(state.turn_word, "lobster")
        prompt = state.correction_prompt()
        self.assertIn("show_learning_image", prompt)
        self.assertIn("lobster", prompt)
        self.assertIn("Con tôm hốp sống ở đâu", prompt)

    def test_correction_preserves_color_count_and_image_style_request(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem ảnh một con mèo màu cam dạng hoạt hình")
        state.observe_assistant("Cat nghĩa là con mèo.")
        prompt = state.correction_prompt()
        self.assertIn("cat", prompt)
        self.assertIn("một con mèo màu cam dạng hoạt hình", prompt)
        self.assertIn("precise English query", prompt)

    def test_abstract_normal_conversation_does_not_force_image(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Hôm nay bé cảm thấy rất vui")
        state.observe_assistant("Wisio vui cùng bé nè!")
        self.assertIsNone(state.correction_prompt())

    def test_same_concrete_topic_is_not_repeated_on_next_turn(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Kể cho bé nghe về con voi")
        state.mark_image("elephant")
        state.finish_turn()
        state.observe_user("Con voi sống ở đâu?")
        self.assertIsNone(state.correction_prompt())

    def test_explicit_image_request_can_refresh_same_subject(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Kể cho bé nghe về con voi")
        state.mark_image("elephant")
        state.finish_turn()
        state.observe_user("Cho xem hình con voi màu trắng")
        self.assertIsNotNone(state.correction_prompt())

    def test_streamed_transcript_keeps_attributes_before_and_after_subject(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem ảnh")
        state.observe_user("một con mèo")
        state.observe_user("màu cam dạng hoạt hình")
        self.assertEqual(state.turn_word, "cat")
        self.assertIn("Cho xem ảnh một con mèo màu cam dạng hoạt hình",
                      state.correction_prompt())

    def test_direct_fallback_builds_precise_english_query(self):
        state = learning_session.LearningVisualState()
        state.observe_user("Cho xem ảnh hai con mèo màu cam dạng hoạt hình")
        self.assertIsNotNone(state.correction_prompt())
        self.assertEqual(state.fallback_request(),
                         ("cat", "two orange cat cartoon"))


if __name__ == "__main__":
    unittest.main()
