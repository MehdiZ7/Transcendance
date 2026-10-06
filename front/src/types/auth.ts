export interface RegisterInput {
  email: string;
  password: string;
  display_name: string;
}

export interface PasswordLoginInput {
  email: string;
  password: string;
}

export interface ChangePasswordInput {
  new_password: string;
  current_password?: string;
}
