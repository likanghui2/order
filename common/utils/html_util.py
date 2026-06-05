from bs4 import BeautifulSoup


class HtmlUtil:

    @staticmethod
    def parse_html_form_data(html_data: str) -> dict:
        soup = BeautifulSoup(html_data, 'lxml')
        form_data = soup.find('form')
        input_data = form_data.find_all('input')

        input_dict = {}
        for i in input_data:
            if i.attrs.get('value') is not None and i.attrs.get('name'):
                input_dict[i.attrs['name']] = i.attrs['value']
            elif i.attrs.get('name'):
                input_dict[i.attrs['name']] = ''

        return input_dict