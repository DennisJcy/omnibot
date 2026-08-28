import unittest

from omnibot.simphtml import extract_page_structure


class PageStructureExtractorTests(unittest.TestCase):
    def test_extracts_title_headings_links_controls_forms_and_lists(self):
        html = """
        <main>
          <h1>Search Results</h1>
          <h2>Repositories</h2>
          <form action="/search">
            <input id="q" name="q" type="search" placeholder="Search GitHub" value="ai" />
            <button type="submit">Search</button>
          </form>
          <article>
            <h3><a href="https://github.com/example/alpha">example / alpha</a></h3>
            <p>Alpha project description.</p>
          </article>
          <article>
            <h3><a href="/example/beta">example / beta</a></h3>
            <p>Beta project description.</p>
          </article>
          <nav><a href="/login">Sign in</a></nav>
        </main>
        """

        result = extract_page_structure(html)

        self.assertEqual(result["headings"][:2], [
            {"level": 1, "text": "Search Results"},
            {"level": 2, "text": "Repositories"},
        ])
        self.assertIn(
            {"text": "example / alpha", "href": "https://github.com/example/alpha"},
            result["links"],
        )
        self.assertIn(
            {"text": "example / beta", "href": "/example/beta"},
            result["links"],
        )
        self.assertIn(
            {"tag": "input", "type": "search", "id": "q", "name": "q", "label": "", "placeholder": "Search GitHub", "value": "ai"},
            result["controls"],
        )
        self.assertIn(
            {"tag": "button", "type": "submit", "id": "", "name": "", "label": "Search", "placeholder": "", "value": ""},
            result["controls"],
        )
        self.assertEqual(result["forms"], [{"action": "/search", "method": "", "controls": ["q", "Search"]}])
        self.assertEqual(result["list_candidates"][0]["item_count"], 2)
        self.assertEqual(result["list_candidates"][0]["items"][0]["title"], "example / alpha")

    def test_limits_large_pages_to_predictable_counts(self):
        html = "<main>" + "".join(
            f'<p><a href="/item-{i}">Item {i}</a></p>' for i in range(80)
        ) + "</main>"

        result = extract_page_structure(html)

        self.assertEqual(len(result["links"]), 50)
        self.assertEqual(result["links"][0], {"text": "Item 0", "href": "/item-0"})
        self.assertEqual(result["links"][-1], {"text": "Item 49", "href": "/item-49"})


if __name__ == "__main__":
    unittest.main()
