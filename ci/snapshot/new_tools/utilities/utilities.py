import logging


def is_substring_ignore_case(str1, str2):
    return str1.lower() in str2.lower()

def find_string_match(string, strings):
    matches = [str for str in strings if is_substring_ignore_case(string, str)]
    if len(matches) == 1:
        return matches[0]
    logging.info("No single match for %s in %s: Found matches %s",
                 string, strings, matches)
    return None