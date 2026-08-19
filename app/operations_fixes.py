from flask import Blueprint,flash,redirect,render_template,request,url_for
from flask_login import current_user,login_required
from . import db
from .models import Asset,IntegrationConnector,IntegrationSignalMapping
ops_bp=Blueprint('ops',__name__)
def tid():return current_user.customer_id
@ops_bp.route('/asset/<int:asset_id>/settings',methods=['GET','POST'])
@login_required
def asset_settings(asset_id):
 a=Asset.query.filter_by(id=asset_id,customer_id=tid()).first_or_404()
 if request.method=='POST':
  a.name=request.form.get('name','').strip() or a.name
  cap=request.form.get('capacity','').strip();a.capacity=float(cap) if cap else None;a.capacity_unit=request.form.get('capacity_unit','L').strip() or 'L';db.session.commit();flash('Asset settings updated.','ok');return redirect(url_for('main.asset_view',asset_id=a.id))
 return render_template('asset_settings.html',asset=a)
def mapping_total(customer_id):
 total=IntegrationSignalMapping.query.filter_by(customer_id=customer_id).count()
 try:
  from .models import MqttTopicMapping,UniversalSourceMapping
  total+=MqttTopicMapping.query.filter_by(customer_id=customer_id).count();total+=UniversalSourceMapping.query.filter_by(customer_id=customer_id).count()
 except (ImportError,AttributeError):pass
 return total
