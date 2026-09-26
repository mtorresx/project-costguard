addon user {
  input {
    int user_id? {
      table = ""
    }
  }

  stack {
    db.query "" {
      where = $db.user.id == $input.user_id
      return = {type: "single"}
    }
  }

  guid = "NoXYqQutp645iuNSSkC2lyi57UQ"
}