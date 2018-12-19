from tippicserver import db
from tippicserver.models import SystemConfig, User, UUIDType, get_user_app_data
from tippicserver.utils import InvalidUsage


class ReportedPictures(db.Model):
    picture_id = db.Column(db.String(40), nullable=False, primary_key=True)
    reporter_id = db.Column('user_id', UUIDType(binary=False), db.ForeignKey("user.user_id"), primary_key=True,
                            nullable=False)


class Picture(db.Model):
    """
    the represents a single picture
    """
    picture_id = db.Column(db.String(40), nullable=False, primary_key=True)
    picture_order_index = db.Column(db.Integer(), nullable=False, primary_key=False)
    title = db.Column(db.String(80), nullable=False, primary_key=False)
    image_url = db.Column(db.String(200), nullable=False, primary_key=False)
    author = db.Column(db.JSON)
    min_client_version_ios = db.Column(db.String(10), nullable=False, primary_key=False)
    update_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now())
    is_active = db.Column(db.Boolean, unique=False, default=True)

    def __repr__(self):
        return '<picture_id: %s, min_client_version_ios: %s, delay_days: %s>' % \
               (self.picture_id, self.min_client_version_ios, self.delay_days)


def picture_to_json(picture):
    """converts the given picture object to a json-representation"""
    if not picture:
        return {}
    # build the json object:
    picture_json = {}
    picture_json['picture_id'] = picture.picture_id
    picture_json['title'] = picture.title
    picture_json['image_url'] = picture.image_url
    picture_json['author'] = picture.author

    # add picture author name
    user = User.query.filter_by(User.user_id == picture.picture_id).first()
    if user:
        picture_json['author']['name'] = user.username

    return picture_json


def get_picture_for_user(user_id):
    """ get next picture for this user"""
    system_config = SystemConfig.query.first()
    user_app_data = get_user_app_data(user_id)

    if system_config is None:
        # deliver the first image in the order
        new_picture = Picture.query.order_by(Picture.picture_order_index).first()
        # if user is blocked, return error message
        if new_picture.author['user_id'] in user_app_data:
            return {"error": "blocked_user"}
        # we might not have images in the db at all
        if new_picture is None:
            return {}

        try:
            # store the delivered image information
            system_config = SystemConfig()
            system_config.current_picture_index = new_picture.picture_order_index
            db.session.add(system_config)
            db.session.commit()
        except Exception as e:
            print(e)
            print('cant get_picture_for_user with user_id %s' % user_id)
            return {}
        return picture_to_json(new_picture)
    else:
        # TODO: cache this
        # deliver the current picture
        new_picture = Picture.query.filter_by(picture_order_index=system_config.current_picture_index).first()
        if not new_picture:
            return {}
        return picture_to_json(new_picture)


def set_picture_active(picture_id, is_active):
    """enable/disable picture by offer_id"""
    picture = Picture.query.filter_by(picture_id=picture_id).first()
    if not picture:
        raise InvalidUsage('no such picture_id')
    picture.is_active = is_active
    try:
        db.session.add(picture)
        db.session.commit()
    except Exception as e:
        print(e)
        print('cant set_picture_active with picture_id %s' % picture_id)
        return False

    return True


def add_picture(picture_json, set_active=True):
    """adds an picture to the db"""
    import uuid, json
    print(picture_json)

    picture = Picture()
    try:
        picture.picture_id = str(uuid.uuid4())
        picture.title = picture_json['title']
        picture.image_url = picture_json['image_url']
        picture.author = picture_json['author']
        picture.picture_order_index = picture_json['picture_order_index']
        picture.min_client_version_ios = picture_json.get('min_client_version_ios', "1.0")

        db.session.add(picture)
        db.session.commit()
    except Exception as e:
        print(e)
        print('cant add picture to db with picture_id %s' % picture.picture_id)
        return False
    else:
        if set_active:
            set_picture_active(picture.picture_id, True)
        return True
