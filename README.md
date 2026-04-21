# RSS Feed Generator <!-- omit in toc -->

Forked from https://github.com/Olshansk/rss-feeds

RSS feeds in newest first order.

## tl;dr Available RSS Feeds <!-- omit in toc -->

| Blog                                                           | Feed                                                                                                                              |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| [Anthropic Engineering](https://www.anthropic.com/engineering) | [feed_anthropic_engineering.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_anthropic_engineering.xml) |
| [Anthropic Research](https://www.anthropic.com/research)       | [feed_anthropic_research.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_anthropic_research.xml)       |
| [Thinking Machines Lab](https://thinkingmachines.ai/blog/)     | [feed_thinkingmachines.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_thinkingmachines.xml)           |
| [Thinking Machines News](https://thinkingmachines.ai/news/)    | [feed_thinkingmachines_news.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_thinkingmachines_news.xml) |
| [Noumena Research](https://www.noumena.com/research)           | [feed_noumena.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_noumena.xml)                             |
| [Dao-AILab Blog](https://dao-lab.ai/blog/)                     | [feed_dao_ailab.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_dao_ailab.xml)                         |
| [leloykun's Ponder](https://leloykun.github.io/ponder/)        | [feed_leloykun.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_leloykun.xml)                           |
| [Claude Blog](https://claude.com/blog/)                         | [feed_claude_blog.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_claude_blog.xml)                     |
| [Transformer Circuits Thread](https://transformer-circuits.pub/) | [feed_transformer_circuits.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_transformer_circuits.xml) |
| [People Daily](https://plink.anyfeeder.com/people-daily) | [feed_people_daily.xml](https://raw.githubusercontent.com/himalalps/rss-feeds/main/feeds/feed_people_daily.xml) |

## RSS Feed Generator

The goal of this project is to generate rss (feed.xml) files from web pages (\*.html) that contain blogs or updates but do not provide a subscribe button or a default RSS feed.

Here is the expected flow and instructions:

1. You will be given an HTML file that needs to be parsed and understood.

2. You will provide a python script that writes a `feed_{}.xml` file that is RSS feed compatible.

3. The `{}` in `feed_{}.xml` will refer to the name of a particular RSS feed.

4. GitHub actions will take care of triggering this periodically, so you don't have to worry about it

5. If you are not given an HTML file that you can parse into an rss feed, either ask for it or explain what the issue with the provided file is.

6. Use existing feeds and parsers as a reference.

7. Update the table in the README.md file with the new feed once you are done


## Usage

```bash
pip install uv
uv venv
uv sync
```
