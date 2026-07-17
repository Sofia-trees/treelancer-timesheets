-- Trees Engineering — Treelancer Timesheets: Postgres DDL
-- Generated from backend/app/models.py (SQLAlchemy 2.0).
-- (In the app these are created by SQLAlchemy/Alembic; listed here so the
--  file is runnable standalone.)

CREATE TYPE user_role AS ENUM ('freelancer', 'line_manager', 'admin');
CREATE TYPE timesheet_status AS ENUM ('draft', 'submitted', 'manager_approved', 'approved', 'rejected');
CREATE TYPE approval_action AS ENUM ('submitted', 'manager_approved', 'manager_rejected', 'admin_approved', 'admin_rejected', 'reopened');
CREATE TYPE day_off_code AS ENUM ('OFF');

CREATE TABLE clients (
	id UUID NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE users (
	id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	role user_role NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	designation VARCHAR(200), 
	client_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_line_manager_has_client CHECK ((role = 'line_manager') = (client_id IS NOT NULL)), 
	UNIQUE (email), 
	FOREIGN KEY(client_id) REFERENCES clients (id)
);

CREATE TABLE assignments (
	id UUID NOT NULL, 
	freelancer_id UUID NOT NULL, 
	client_id UUID NOT NULL, 
	line_manager_id UUID, 
	position VARCHAR(200) NOT NULL, 
	po_code VARCHAR(100), 
	line_manager_name VARCHAR(200), 
	line_manager_designation VARCHAR(200), 
	default_work_location VARCHAR(200), 
	start_date DATE NOT NULL, 
	end_date DATE, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(freelancer_id) REFERENCES users (id), 
	FOREIGN KEY(client_id) REFERENCES clients (id), 
	FOREIGN KEY(line_manager_id) REFERENCES users (id)
);

CREATE TABLE magic_link_tokens (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	consumed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (token_hash)
);

CREATE TABLE timesheets (
	id UUID NOT NULL, 
	assignment_id UUID NOT NULL, 
	freelancer_id UUID NOT NULL, 
	billing_period DATE NOT NULL, 
	status timesheet_status NOT NULL, 
	client_project VARCHAR(200) NOT NULL, 
	resource_name VARCHAR(200) NOT NULL, 
	position VARCHAR(200) NOT NULL, 
	po_code VARCHAR(100), 
	line_manager_name VARCHAR(200), 
	line_manager_designation VARCHAR(200), 
	total_standard_hours NUMERIC(6, 2) NOT NULL, 
	total_overtime_hours NUMERIC(6, 2) NOT NULL, 
	overtime_multiplier NUMERIC(4, 2) NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	signature_name VARCHAR(200), 
	signature_confirmed BOOLEAN NOT NULL, 
	date_signed DATE, 
	manager_action_at TIMESTAMP WITH TIME ZONE, 
	manager_action_by UUID, 
	admin_action_at TIMESTAMP WITH TIME ZONE, 
	admin_action_by UUID, 
	rejection_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_timesheet_period UNIQUE (assignment_id, billing_period), 
	FOREIGN KEY(assignment_id) REFERENCES assignments (id), 
	FOREIGN KEY(freelancer_id) REFERENCES users (id), 
	FOREIGN KEY(manager_action_by) REFERENCES users (id), 
	FOREIGN KEY(admin_action_by) REFERENCES users (id)
);

CREATE TABLE approval_events (
	id UUID NOT NULL, 
	timesheet_id UUID NOT NULL, 
	actor_id UUID NOT NULL, 
	action approval_action NOT NULL, 
	reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(timesheet_id) REFERENCES timesheets (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE timesheet_entries (
	id UUID NOT NULL, 
	timesheet_id UUID NOT NULL, 
	day INTEGER NOT NULL, 
	standard_hours NUMERIC(4, 2) NOT NULL, 
	overtime_hours NUMERIC(4, 2) NOT NULL, 
	work_location VARCHAR(200), 
	remarks TEXT, 
	day_off_code day_off_code, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_entry_day UNIQUE (timesheet_id, day), 
	CONSTRAINT ck_entry_day_range CHECK (day BETWEEN 1 AND 31), 
	CONSTRAINT ck_entry_hours_nonneg CHECK (standard_hours >= 0 AND overtime_hours >= 0), 
	CONSTRAINT ck_off_has_no_hours CHECK (day_off_code IS NULL OR (standard_hours = 0 AND overtime_hours = 0)), 
	FOREIGN KEY(timesheet_id) REFERENCES timesheets (id) ON DELETE CASCADE
);
