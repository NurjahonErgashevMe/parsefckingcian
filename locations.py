import cianparser

moscow_parser = cianparser.CianParser(location="Тюмень")
data = moscow_parser.get_flats(deal_type="sale", rooms=(1,2), additional_settings={
            "start_page": 1,
            "end_page": 1})