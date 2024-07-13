import requests
from bs4 import BeautifulSoup, Comment
import pandas as pd
from time import sleep
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TAG_MAPPING = {
    'strike': 's',
    'u': 'span class="underline"',
    'b': 'strong',
    'i': 'em',
    'center': 'div style="text-align: center;"',
    'font': 'span',
    'big': 'span style="font-size: larger;"',
    'tt': 'code',
    'abbr': 'span class="abbr"',
    'acronym': 'span class="acronym"',
    'dir': 'ul',
    'menu': 'ul',
    'applet': 'object',
    'basefont': 'span',
    'frame': 'iframe',
    'frameset': 'iframe',
    'noframes': 'iframe',
    'xmp': 'pre',
    'plaintext': 'pre',
    'h1': 'h2',
    'h3': 'h2',
    'h4': 'h2',
    'h5': 'h2',
    'h6': 'h2',
}

ALLOWED_TAGS = ['div', 'article', 'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'small', 'a', 'button']

def replaceDeprecatedTags(htmlContent):
    soup = BeautifulSoup(htmlContent, 'html.parser')
    
    # Remove comments from soup
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        comment.extract()
    
    # Remove script tags and their contents
    for script in soup.find_all('script'):
        script.extract()

    # Remove specific CSS blocks
    for style_tag in soup.find_all('style'):
        style_text = style_tag.get_text()
        if 'webapp-compat-navigation:not(.WebappCompatPlaceholder)' in style_text \
                or 'webapp-compat-navigation-empty:not(.WebappCompatPlaceholder)' in style_text \
                or 'webapp-compat-seo-navbar.WebappCompatPlaceholder' in style_text \
                or 'app-seo-navbar' in style_text:
            style_tag.extract()

    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            if tag.name in TAG_MAPPING:
                newTag = TAG_MAPPING[tag.name]
                if newTag.startswith('<'):
                    newTag = BeautifulSoup(newTag, 'html.parser').find()
                    tag.replace_with(newTag)
                else:
                    tag.name = newTag
            else:
                tag.unwrap()  # Remove tags not in allowed list
        else:
            if tag.name == 'a':
                href = tag.get('href')
                if href and not href.startswith('http'):
                    tag.unwrap()
                else:
                    tag.attrs = {}  # Remove all attributes from 'a' tags
            else:
                tag.attrs = {}  # Remove all attributes from other allowed tags
            
    return str(soup)

def extractTextWithHtml(articleSoup):
    body_tag = articleSoup.find('body')
    if body_tag:
        return str(body_tag)
    else:
        return ""

def initializeDriver():
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

def getArticles(domain, categoryKeyword, numArticles=10, selectors=None):
    articles = []
    page = 1
    driver = initializeDriver()

    while True:
        url = urljoin(domain, f"?page={page}")
        logging.info(f"Fetching URL: {url}")
        
        driver.get(url)
        sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        articleElements = []
        articleSelector = selectors.get('article', {})
        if articleSelector['type'] == 'tag':
            articleElements = soup.find_all(articleSelector['name'])
        elif articleSelector['type'] == 'class':
            articleElements = soup.find_all(class_=articleSelector['name'])
        else:
            logging.error(f"Unsupported selector type: {articleSelector['type']}")
            continue

        if not articleElements:
            logging.info("No more articles found.")
            break

        for article in articleElements:
            try:
                if selectors['title']['type'] == 'class':
                    titleElement = article.find(class_=selectors['title']['name'])
                elif selectors['title']['type'] == 'tag':
                    titleElement = article.find(selectors['title']['name'])

                if not titleElement:
                    logging.warning("Title element not found")
                    continue
                title = titleElement.get_text(strip=True)
                
                linkElement = article.find('a')
                if not linkElement or 'href' not in linkElement.attrs:
                    logging.warning("Link element not found or missing href attribute")
                    continue
                link = linkElement['href']
                
                dateElement = article.find(selectors['date']['type'], selectors['date']['name'])
                date = dateElement.get_text(strip=True) if dateElement else ''
                
                fullLink = urljoin(domain, link)
                logging.info(f"Visiting article URL: {fullLink}")
                driver.get(fullLink)
                sleep(2)
                articleSoup = BeautifulSoup(driver.page_source, 'html.parser')

                content_with_html = extractTextWithHtml(articleSoup)
                content = replaceDeprecatedTags(content_with_html)

                if re.search(re.escape(categoryKeyword).replace('\\*', '.*'), fullLink, re.IGNORECASE) \
                        or re.search(re.escape(categoryKeyword).replace('\\*', '.*'), title, re.IGNORECASE):
                    articles.append({
                        'title': title,
                        'link': fullLink,
                        'date': date,
                        'content': content,
                        'content_with_html': content_with_html
                    })

                if len(articles) >= numArticles:
                    break
            except AttributeError as e:
                logging.error(f"Error processing article: {e}")

        if len(articles) >= numArticles:
            break

        page += 1
        sleep(1)

    driver.quit()
    return articles

def saveToExcel(articles, filename):
    df = pd.DataFrame(articles)
    df.to_excel(filename, index=False)
    logging.info(f"Data saved to {filename}")

def saveToCsv(articles, filename):
    df = pd.DataFrame(articles)
    df.to_csv(filename, index=False)
    logging.info(f"Data saved to {filename}")

# Usage example
domain = "https://www.freelancer.com/community/freelancing"
categoryKeyword = "freelance"
selectors = {
    'article': {
        'type': 'tag',
        'name': 'article',
    },
    'title': {
        'type': 'tag',
        'name': 'h3',
    },
    'date': {
        'type': 'class',
        'name': 'article-date'
    },
    'content': {
        'type': 'class',
        'name': 'article-content'
    }
}
articles = getArticles(domain, categoryKeyword, numArticles=10, selectors=selectors)
# saveToExcel(articles, "articles.xlsx")
saveToCsv(articles, "articles.csv")
