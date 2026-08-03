import random


def generate_random_number() -> int:
    """Return a random whole number between 1 and 1000."""
    return random.randint(1, 1000)


def analyze_number(number: int, random_number: int) -> str:
    """Compare the user's number with a generated random number."""
    if number < random_number:
        comparison = "less than"
    elif number > random_number:
        comparison = "greater than"
    else:
        comparison = "equal to"

    return f"{number} is {comparison} {random_number}."

